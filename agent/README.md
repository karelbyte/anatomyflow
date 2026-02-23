# Agent (Schema extractor)

Go binary that connects to a MySQL or PostgreSQL database and outputs the schema (tables and columns) as JSON. No sensitive row data is read; only metadata from `information_schema` is used.

**Solo lo que hay en la DB:** El agente se atiene exclusivamente a la conexión configurada. Las tablas y columnas que envía (al archivo JSON y al backend por WebSocket) son únicamente las que existen en esa base de datos; no se añaden tablas de otros orígenes ni se lee ningún schema desde archivos.

## Requirements

- Go 1.21+

## Build

```bash
cd agent
go mod tidy
go build -o schema-extractor .
```

On Windows use an explicit `.exe` name so the system runs it as an executable:

```powershell
go build -o schema-extractor.exe .
```

## Configuration

Connection can be provided in two ways.

### 1. Config file (recommended)

Use a JSON or YAML file with either a **connection string** or **host/port/user/password/database**.

**Option A – connection string:**

```yaml
driver: postgres
connection_string: "postgres://user:pass@localhost:5432/mydb?sslmode=disable"
```

**Option B – host, port, user, password, database:**

```yaml
driver: postgres
host: localhost
port: 5432
user: myuser
password: mypass
database: mydb
sslmode: disable
```

For MySQL use `driver: mysql`; default port is 3306. For Postgres default port is 5432. `sslmode` applies only to Postgres.

**Enviar schema al backend ProjectAnatomy (opcional):** Si en el config añades `backend_ws_url` y `backend_api_key`, al extraer el schema el agente lo enviará por WebSocket al backend. Así la app muestra "Schema recibido" y puedes ejecutar el análisis desde el front.

```yaml
backend_ws_url: "ws://localhost:8000/ws/agent"
backend_api_key: "el_api_key_del_proyecto"
```

El `backend_api_key` lo obtienes al crear un proyecto en el frontend de ProjectAnatomy.

Example files: `config.example.yaml`, `config.example.json`, `config.connection-string.example.yaml`. Para enviar el schema al backend: `config.backend.example.yaml`, `config.backend.example.json`.

Run with config file:

```bash
./schema-extractor -config config.yaml
./schema-extractor -config config.json
```

### 2. Flags / environment (no config file)

```bash
./schema-extractor -db mysql -dsn "user:password@tcp(localhost:3306)/database_name"
./schema-extractor -db postgres -dsn "postgres://user:password@localhost:5432/database_name?sslmode=disable"
```

Or set `DB_DSN` and use `-db`:

```bash
set DB_DSN=user:password@tcp(localhost:3306)/database_name
./schema-extractor -db mysql
```

## Output

The schema is written to a file named after the database: `{database}.json` (e.g. `myapp.json`). Invalid filename characters in the database name are replaced with `_`. The path is the current directory. A line is printed to stderr: `Schema written to myapp.json`.

Example content of `myapp.json`:

```json
{
  "database": "myapp",
  "tables": [
    {
      "name": "users",
      "columns": [
        { "name": "id", "type": "int" },
        { "name": "email", "type": "varchar" }
      ]
    }
  ]
}
```

Use that file with the analyzer:

```bash
python extract_deps.py myapp.json path/to/Controller.php --out graph.json
```
