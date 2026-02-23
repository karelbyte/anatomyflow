package main

import (
	"database/sql"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"regexp"

	_ "github.com/go-sql-driver/mysql"
	_ "github.com/lib/pq"
)

var safeFilenameRe = regexp.MustCompile(`[^a-zA-Z0-9_-]`)

type Column struct {
	Name string `json:"name"`
	Type string `json:"type"`
}

type Table struct {
	Name    string   `json:"name"`
	Columns []Column `json:"columns"`
}

type Schema struct {
	Database string  `json:"database"`
	Tables   []Table `json:"tables"`
}

func main() {
	configPath := flag.String("config", "", "Path to config file (JSON or YAML). If set, connection is read from file instead of -dsn/-db.")
	dbType := flag.String("db", "mysql", "Database type: mysql or postgres (used when -config is not set)")
	dsn := flag.String("dsn", "", "Connection string (used when -config is not set)")
	flag.Parse()

	var driver string
	var connectionString string

	var fileCfg *Config
	if *configPath != "" {
		dsn, cfg, err := loadConfig(*configPath)
		if err != nil {
			fmt.Fprintf(os.Stderr, "error: load config: %v\n", err)
			os.Exit(1)
		}
		driver = dsn.driver
		connectionString = dsn.dsn
		fileCfg = cfg
	} else {
		if *dsn == "" {
			connectionString = os.Getenv("DB_DSN")
			if connectionString == "" {
				fmt.Fprintf(os.Stderr, "error: provide -config, -dsn, or DB_DSN environment variable\n")
				os.Exit(1)
			}
		} else {
			connectionString = *dsn
		}
		switch *dbType {
		case "mysql":
			driver = "mysql"
		case "postgres", "postgresql":
			driver = "postgres"
		default:
			fmt.Fprintf(os.Stderr, "error: unsupported db type %q (use mysql or postgres)\n", *dbType)
			os.Exit(1)
		}
	}

	db, err := sql.Open(driver, connectionString)
	if err != nil {
		fmt.Fprintf(os.Stderr, "error: open connection: %v\n", err)
		os.Exit(1)
	}
	defer db.Close()

	if err := db.Ping(); err != nil {
		fmt.Fprintf(os.Stderr, "error: ping: %v\n", err)
		os.Exit(1)
	}

	// Schema is exclusively from the established DB connection (information_schema).
	// No tables are read from files or added by hand; only what exists in the connected database is sent.
	var schema Schema
	if driver == "mysql" {
		schema, err = extractMySQLSchema(db)
	} else {
		schema, err = extractPostgresSchema(db)
	}
	if err != nil {
		fmt.Fprintf(os.Stderr, "error: extract schema: %v\n", err)
		os.Exit(1)
	}

	outName := safeFilenameRe.ReplaceAllString(schema.Database, "_") + ".json"
	if outName == ".json" {
		outName = "schema.json"
	}
	f, err := os.Create(outName)
	if err != nil {
		fmt.Fprintf(os.Stderr, "error: create file: %v\n", err)
		os.Exit(1)
	}
	defer f.Close()
	enc := json.NewEncoder(f)
	enc.SetIndent("", "  ")
	if err := enc.Encode(schema); err != nil {
		fmt.Fprintf(os.Stderr, "error: write json: %v\n", err)
		os.Exit(1)
	}
	fmt.Fprintf(os.Stderr, "Schema written to %s\n", outName)

	if fileCfg != nil && fileCfg.BackendWSURL != "" && fileCfg.BackendAPIKey != "" {
		if err := sendSchemaToBackend(fileCfg.BackendWSURL, fileCfg.BackendAPIKey, schema); err != nil {
			fmt.Fprintf(os.Stderr, "warning: send schema to backend: %v\n", err)
		} else {
			fmt.Fprintf(os.Stderr, "Schema sent to backend\n")
		}
	}
}

func extractMySQLSchema(db *sql.DB) (Schema, error) {
	var dbName string
	if err := db.QueryRow("SELECT DATABASE()").Scan(&dbName); err != nil {
		return Schema{}, err
	}
	schema := Schema{Database: dbName}

	rows, err := db.Query("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = ? AND TABLE_TYPE = 'BASE TABLE' ORDER BY TABLE_NAME", dbName)
	if err != nil {
		return Schema{}, err
	}
	defer rows.Close()

	var tableNames []string
	for rows.Next() {
		var name string
		if err := rows.Scan(&name); err != nil {
			return Schema{}, err
		}
		tableNames = append(tableNames, name)
	}
	if err := rows.Err(); err != nil {
		return Schema{}, err
	}

	for _, tableName := range tableNames {
		t := Table{Name: tableName}
		colRows, err := db.Query("SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? ORDER BY ORDINAL_POSITION", dbName, tableName)
		if err != nil {
			return Schema{}, err
		}
		for colRows.Next() {
			var c Column
			if err := colRows.Scan(&c.Name, &c.Type); err != nil {
				colRows.Close()
				return Schema{}, err
			}
			t.Columns = append(t.Columns, c)
		}
		colRows.Close()
		if err := colRows.Err(); err != nil {
			return Schema{}, err
		}
		schema.Tables = append(schema.Tables, t)
	}
	return schema, nil
}

func extractPostgresSchema(db *sql.DB) (Schema, error) {
	var dbName string
	if err := db.QueryRow("SELECT current_database()").Scan(&dbName); err != nil {
		return Schema{}, err
	}
	schema := Schema{Database: dbName}

	rows, err := db.Query("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name")
	if err != nil {
		return Schema{}, err
	}
	defer rows.Close()

	var tableNames []string
	for rows.Next() {
		var name string
		if err := rows.Scan(&name); err != nil {
			return Schema{}, err
		}
		tableNames = append(tableNames, name)
	}
	if err := rows.Err(); err != nil {
		return Schema{}, err
	}

	for _, tableName := range tableNames {
		t := Table{Name: tableName}
		colRows, err := db.Query("SELECT column_name, data_type FROM information_schema.columns WHERE table_schema = 'public' AND table_name = $1 ORDER BY ordinal_position", tableName)
		if err != nil {
			return Schema{}, err
		}
		for colRows.Next() {
			var c Column
			if err := colRows.Scan(&c.Name, &c.Type); err != nil {
				colRows.Close()
				return Schema{}, err
			}
			t.Columns = append(t.Columns, c)
		}
		colRows.Close()
		if err := colRows.Err(); err != nil {
			return Schema{}, err
		}
		schema.Tables = append(schema.Tables, t)
	}
	return schema, nil
}
