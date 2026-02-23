# Frontend (Graph visualizer)

React app (Vite) with React Flow that displays the dependency graph produced by the analyzer. You can load a graph JSON file or use the default sample graph.

## Requirements

- Node.js 18+

## Setup

```bash
cd frontend
npm install
```

## Run

```bash
npm run dev
```

Open the URL shown (e.g. http://localhost:5173). Use **Load graph JSON** in the header to select a `graph.json` file from the analyzer, or use `public/sample-graph.json` to try without running the analyzer. The graph is interactive: pan, zoom, drag nodes. MiniMap and Controls are available.

## Build

```bash
npm run build
npm run preview
```

## Graph JSON format

Expected format (same as analyzer output):

```json
{
  "nodes": [
    { "id": "table:orders", "type": "default", "position": { "x": 0, "y": 0 }, "data": { "label": "orders", "kind": "table" } }
  ],
  "edges": [
    { "id": "e1", "source": "table:orders", "target": "model:Order" }
  ]
}
```

`kind` is used for MiniMap colors (table, model, controller, route).
