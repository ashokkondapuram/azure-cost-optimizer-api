/** Legacy explorer tab ids — inventory-only surface at `/explorer`. */
export const EXPLORER_TABS = [
  { id: 'inventory', label: 'Inventory' },
];

/** @deprecated Explorer is inventory-only; provider kept for legacy panel imports. */
export function CloudExplorerProvider({ children }) {
  return children;
}

/** @deprecated */
export function useCloudExplorer() {
  return { tab: 'inventory', setTab: () => {} };
}
