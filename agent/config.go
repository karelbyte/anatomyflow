package main

import (
	"encoding/json"
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"gopkg.in/yaml.v3"
)

type Config struct {
	Driver           string `json:"driver" yaml:"driver"`
	ConnectionString string `json:"connection_string" yaml:"connection_string"`
	Host             string `json:"host" yaml:"host"`
	Port             int    `json:"port" yaml:"port"`
	User             string `json:"user" yaml:"user"`
	Password         string `json:"password" yaml:"password"`
	Database         string `json:"database" yaml:"database"`
	SslMode          string `json:"sslmode" yaml:"sslmode"`
	BackendWSURL     string `json:"backend_ws_url" yaml:"backend_ws_url"`
	BackendAPIKey    string `json:"backend_api_key" yaml:"backend_api_key"`
}

type driverDSN struct {
	driver string
	dsn    string
}

func loadConfig(path string) (driverDSN, *Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return driverDSN{}, nil, err
	}
	var c Config
	ext := strings.ToLower(filepath.Ext(path))
	switch ext {
	case ".yml", ".yaml":
		if err := yaml.Unmarshal(data, &c); err != nil {
			return driverDSN{}, nil, fmt.Errorf("yaml: %w", err)
		}
	case ".json":
		if err := json.Unmarshal(data, &c); err != nil {
			return driverDSN{}, nil, fmt.Errorf("json: %w", err)
		}
	default:
		return driverDSN{}, nil, fmt.Errorf("unsupported config extension %q (use .json, .yml or .yaml)", ext)
	}
	dsn, err := configToDriverDSN(c)
	if err != nil {
		return driverDSN{}, nil, err
	}
	return dsn, &c, nil
}

func configToDriverDSN(c Config) (driverDSN, error) {
	driver := strings.ToLower(strings.TrimSpace(c.Driver))
	if driver == "postgresql" {
		driver = "postgres"
	}
	if driver != "mysql" && driver != "postgres" {
		return driverDSN{}, fmt.Errorf("config driver must be mysql or postgres, got %q", c.Driver)
	}

	if c.ConnectionString != "" {
		return driverDSN{driver: driver, dsn: strings.TrimSpace(c.ConnectionString)}, nil
	}

	if c.Host == "" {
		c.Host = "localhost"
	}
	if c.Port == 0 {
		if driver == "mysql" {
			c.Port = 3306
		} else {
			c.Port = 5432
		}
	}
	if c.Database == "" {
		return driverDSN{}, fmt.Errorf("config database is required when not using connection_string")
	}

	if driver == "mysql" {
		user := c.User
		if c.Password != "" {
			user = user + ":" + c.Password
		}
		dsn := fmt.Sprintf("%s@tcp(%s:%d)/%s", user, c.Host, c.Port, c.Database)
		return driverDSN{driver: "mysql", dsn: dsn}, nil
	}

	return driverDSN{driver: "postgres", dsn: buildPostgresDSN(c)}, nil
}

func buildPostgresDSN(c Config) string {
	port := c.Port
	if port == 0 {
		port = 5432
	}
	sslmode := c.SslMode
	if sslmode == "" {
		sslmode = "disable"
	}
	var sb strings.Builder
	sb.WriteString("postgres://")
	if c.User != "" {
		sb.WriteString(url.PathEscape(c.User))
		if c.Password != "" {
			sb.WriteString(":")
			sb.WriteString(url.PathEscape(c.Password))
		}
		sb.WriteString("@")
	}
	sb.WriteString(c.Host)
	sb.WriteString(":")
	sb.WriteString(strconv.Itoa(port))
	sb.WriteString("/")
	sb.WriteString(c.Database)
	sb.WriteString("?sslmode=")
	sb.WriteString(sslmode)
	return sb.String()
}
