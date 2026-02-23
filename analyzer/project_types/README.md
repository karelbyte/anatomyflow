# Tipos de proyecto

Cada tipo de proyecto define:

- **detect(root_path)**: si esta carpeta es un proyecto de este stack.
- **extensions**: extensiones de archivo a escanear (ej. `.php`, `.ts`, `.tsx`).
- **classify(files, base_path)**: clasificación por variante (ej. controllers, models, routes).
- **variants**: por variante, un prompt builder `(schema, code) -> str` y opcionalmente `code_kind` (nodo al que asociar el código).

## Añadir un nuevo stack

1. Crear un módulo, p. ej. `nextjs_hexagonal.py`.
2. Implementar un dict con `name`, `detect`, `extensions`, `classify`, `variants`.
3. En `__init__.py`, añadir el nuevo tipo a la lista devuelta por `get_project_types()`.

El grafo de salida es siempre el mismo formato (nodos/edges); los `kind` pueden ser los estándar (table, model, controller, route) o nuevos para el frontend.
