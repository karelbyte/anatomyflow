"""
Tipos de proyecto soportados por el analizador.
Cada tipo define: detección, extensiones de archivo, clasificación por variante y prompts por variante.
Añadir un nuevo stack (p. ej. Next.js hexagonal) = implementar este contrato y registrarlo aquí.
"""

from project_types.generic_node import GENERIC_NODE
from project_types.laravel import LARAVEL

# Contrato: cada tipo es un dict con:
#   name: str
#   detect(root_path: str) -> bool
#   extensions: tuple[str, ...]  — extensiones a escanear (ej. (".php",) o (".ts", ".tsx"))
#   exclude_dirs: tuple[str, ...]  — (opcional) carpetas a no recorrer, ej. ("vendor", "node_modules")
#   classify(files: list[str], base_path: str) -> dict[str, list[str]]  — variant_name -> paths
#   variants: dict[str, dict]  — variant_name -> {"build_prompt": (schema, code) -> str, "code_kind": str | None}
# code_kind = tipo de nodo al que asociar el código del archivo (ej. "controller", "model"); None = no asociar

def get_project_types():
    """Orden: GENERIC_NODE para todo proyecto Node (descubrimiento sin convenciones); LARAVEL para PHP."""
    return [GENERIC_NODE, LARAVEL]
