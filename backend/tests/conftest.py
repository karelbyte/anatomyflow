"""
Configuración de pytest para el backend.
Usa SQLite en memoria para no depender de Postgres en CI/local.
"""
import os

# Forzar SQLite antes de que se importe db o main
# Forzar siempre SQLite en memoria en tests
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
