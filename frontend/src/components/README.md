# Diseño atómico

Estructura de componentes siguiendo **Atomic Design**:

- **atoms/** — Elementos mínimos: `Badge`, `Button`, `ColorDot`, `Text`.
- **molecules/** — Agrupaciones simples: `FileInputLabel`, `LegendItem`.
- **organisms/** — Bloques de UI completos: `AppHeader`, `CodePanel`, `AnatomyNode`, `ClusterBg`.
- **templates/** — Maquetas de página: `GraphLayout` (header + canvas + panel de código).

Estilos con **Tailwind CSS**; colores dinámicos (p. ej. por tipo de nodo) se mantienen con `style` cuando es necesario.
