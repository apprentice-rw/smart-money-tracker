import { useState } from 'react';

export function useStockDrawer() {
  const [drawerCusip, setDrawerCusip] = useState(null);
  const [drawerName, setDrawerName] = useState(null);

  function openStockDrawer(cusip, issuerName) {
    setDrawerCusip(cusip);
    setDrawerName(issuerName || cusip);
  }

  function closeStockDrawer() {
    setDrawerCusip(null);
    setDrawerName(null);
  }

  return { drawerCusip, drawerName, openStockDrawer, closeStockDrawer };
}
