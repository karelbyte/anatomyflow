"""
Tipos de proyecto soportados por el analizador.
Cada tipo define: detección, extensiones de archivo, clasificación por variante y prompts por variante.
Añadir un nuevo stack = implementar este contrato y registrarlo aquí.
"""

from project_types.generic_node import GENERIC_NODE
from project_types.laravel import LARAVEL
from project_types.nextjs import NEXTJS
from project_types.nestjs import NESTJS
from project_types.express import EXPRESS

# Contrato: cada tipo es un dict con:
#   name: str
#   detect(root_path: str) -> bool
#   extensions: tuple[str, ...]  — extensiones a escanear (ej. (".php",) o (".ts", ".tsx"))
#   exclude_dirs: tuple[str, ...]  — (opcional) carpetas a no recorrer, ej. ("vendor", "node_modules")
#   classify(files: list[str], base_path: str) -> dict[str, list[str]]  — variant_name -> paths
#   variants: dict[str, dict]  — variant_name -> {"build_prompt": (schema, code) -> str, "code_kind": str | None}
# code_kind = tipo de nodo al que asociar el código del archivo (ej. "controller", "model"); None = no asociar

def get_project_types():
    """Orden: tipos específicos primero; generic_node al final para no ganar en proyectos mixtos."""
    return [LARAVEL, NEXTJS, NESTJS, EXPRESS, GENERIC_NODE]


def get_project_type_by_name(name: str):
    """Devuelve el tipo con name dado o None si no existe."""
    if not name or not name.strip():
        return None
    key = name.strip().lower()
    for pt in get_project_types():
        if pt["name"].lower() == key:
            return pt
    return None
