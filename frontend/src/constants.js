export const KIND_CONFIG = {
  table: {
    color: '#40c057',
    bg: 'rgba(64, 192, 87, 0.12)',
    border: '#40c057',
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
}

export const getKindConfig = (kind) => KIND_CONFIG[kind] || { color: '#868e96', bg: 'rgba(134, 142, 150, 0.12)', border: '#868e96', label: kind || 'Node' }
