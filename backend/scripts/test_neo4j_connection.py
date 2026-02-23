#!/usr/bin/env python3
"""
Script para comprobar la conexión a Neo4j usando las variables del .env del backend.
Ejecutar desde la raíz del repo o desde backend:
  cd backend && python scripts/test_neo4j_connection.py
  uv run python scripts/test_neo4j_connection.py
"""
import os
import sys

# Cargar .env del backend (carpeta que contiene este script -> parent = backend)
_script_dir = os.path.dirname(os.path.abspath(__file__))
_backend_dir = os.path.dirname(_script_dir)
_env_path = os.path.join(_backend_dir, ".env")

try:
    from dotenv import load_dotenv
    if os.path.isfile(_env_path):
        load_dotenv(_env_path)
        print(f"[OK] Variables cargadas desde: {_env_path}")
    else:
        print(f"[AVISO] No existe .env en backend: {_env_path}")
        print("        Usando variables de entorno del sistema.")
except ImportError:
    print("[AVISO] python-dotenv no instalado; usando solo variables del sistema.")

uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
user = os.environ.get("NEO4J_USER", "neo4j")
password = os.environ.get("NEO4J_PASSWORD", "")
database = os.environ.get("NEO4J_DATABASE", "neo4j").strip() or "neo4j"

print()
print("Configuración Neo4j (desde .env o sistema):")
print(f"  NEO4J_URI      = {uri}")
print(f"  NEO4J_USER     = {user}")
print(f"  NEO4J_PASSWORD = {'*' * 8 if password else '(vacío)'}")
print(f"  NEO4J_DATABASE = {database}")
print()

if not password:
    print("[ERROR] NEO4J_PASSWORD no está definido. Añádelo al .env del backend.")
    sys.exit(1)

try:
    from neo4j import GraphDatabase
except ImportError:
    print("[ERROR] Paquete 'neo4j' no instalado. Ejecuta: pip install neo4j")
    sys.exit(1)

driver = None
try:
    driver = GraphDatabase.driver(uri, auth=(user, password))
    driver.verify_connectivity()
    print("[OK] Conexión establecida (verify_connectivity).")

    with driver.session(database=database) as session:
        result = session.run("RETURN 1 AS n")
        row = result.single()
        if row and row["n"] == 1:
            print(f"[OK] Consulta de prueba en base de datos '{database}': RETURN 1 -> {row['n']}")

        result = session.run("CALL dbms.components() YIELD name, versions RETURN name, versions[0] AS version")
        for r in result:
            print(f"[INFO] Neo4j: {r['name']} {r['version']}")

    print()
    print("Conexión a Neo4j correcta. El backend podrá usarla para grafo, impacto y huérfanos.")
except Exception as e:
    print(f"[ERROR] No se pudo conectar a Neo4j: {e}")
    sys.exit(1)
finally:
    if driver:
        driver.close()
