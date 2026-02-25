export const KIND_CONFIG = {
  table: {
    color: 'yellow',
    bg: 'rgba(64, 192, 87, 0.12)',
    border: 'yellow',
    label: 'Table',
  },
  model: {
    color: '#cc5de8',
    bg: 'rgba(204, 93, 232, 0.12)',
    border: '#cc5de8',
    label: 'Model',
  },
  controller: {
    color: '#f59f00',
    bg: 'rgba(245, 159, 0, 0.12)',
    border: '#f59f00',
    label: 'Controller',
  },
  route: {
    color: '#339af0',
    bg: 'rgba(51, 154, 240, 0.12)',
    border: '#339af0',
    label: 'Route',
  },
  view: {
    color: '#20c997',
    bg: 'rgba(32, 201, 151, 0.12)',
    border: '#20c997',
    label: 'View',
  },
  style: {
    color: '#fcc419',
    bg: 'rgba(252, 196, 25, 0.12)',
    border: '#fcc419',
    label: 'Style',
  },
  // Next.js
  page: {
    color: '#e64980',
    bg: 'rgba(230, 73, 128, 0.12)',
    border: '#e64980',
    label: 'Page',
  },
  api_route: {
    color: '#15aabf',
    bg: 'rgba(21, 170, 191, 0.12)',
    border: '#15aabf',
    label: 'API Route',
  },
  component: {
    color: '#7950f2',
    bg: 'rgba(121, 80, 242, 0.12)',
    border: '#7950f2',
    label: 'Component',
  },
  // Express
  express_route: {
    color: '#0ca678',
    bg: 'rgba(12, 166, 120, 0.12)',
    border: '#0ca678',
    label: 'Express Route',
  },
  middleware: {
    color: '#748ffc',
    bg: 'rgba(116, 143, 252, 0.12)',
    border: '#748ffc',
    label: 'Middleware',
  },
  // NestJS
  service: {
    color: '#22b8cf',
    bg: 'rgba(34, 184, 207, 0.12)',
    border: '#22b8cf',
    label: 'Service',
  },
  module: {
    color: '#da77f2',
    bg: 'rgba(218, 119, 242, 0.12)',
    border: '#da77f2',
    label: 'Module',
  },
  // Generic (convention-free): repository, use_case, handler, adapter, entity, factory, other
  repository: {
    color: '#20c997',
    bg: 'rgba(32, 201, 151, 0.12)',
    border: '#20c997',
    label: 'Repository',
  },
  use_case: {
    color: '#f59f00',
    bg: 'rgba(245, 159, 0, 0.12)',
    border: '#f59f00',
    label: 'Use Case',
  },
  handler: {
    color: '#3b82f6',
    bg: 'rgba(59, 130, 246, 0.12)',
    border: '#3b82f6',
    label: 'Handler',
  },
  adapter: {
    color: '#8b5cf6',
    bg: 'rgba(139, 92, 246, 0.12)',
    border: '#8b5cf6',
    label: 'Adapter',
  },
  entity: {
    color: '#ec4899',
    bg: 'rgba(236, 72, 153, 0.12)',
    border: '#ec4899',
    label: 'Entity',
  },
  factory: {
    color: '#f97316',
    bg: 'rgba(249, 115, 22, 0.12)',
    border: '#f97316',
    label: 'Factory',
  },
  other: {
    color: '#868e96',
    bg: 'rgba(134, 142, 150, 0.12)',
    border: '#868e96',
    label: 'Other',
  },
}

export const getKindConfig = (kind) => KIND_CONFIG[kind] || { color: '#868e96', bg: 'rgba(134, 142, 150, 0.12)', border: '#868e96', label: kind || 'Node' }
