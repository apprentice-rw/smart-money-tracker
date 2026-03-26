import { useState, useRef, useMemo } from 'react';

export function useCardOrder(institutions) {
  const [cardOrder, setCardOrder] = useState(() => {
    try { return JSON.parse(localStorage.getItem('smt_card_order')) || null; }
    catch { return null; }
  });

  const [aumMap, setAumMap] = useState(() => {
    try { return JSON.parse(localStorage.getItem('smt_aum_map')) || {}; }
    catch { return {}; }
  });

  const orderedInstsRef = useRef([]);

  // ── AUM callback (from InstitutionCard once holdings load) ─────
  function handleAumLoaded(id, aum) {
    setAumMap((prev) => {
      if (prev[id] === aum) return prev;
      const next = { ...prev, [id]: aum };
      localStorage.setItem('smt_aum_map', JSON.stringify(next));
      return next;
    });
  }

  function resetOrder() {
    setCardOrder(null);
    localStorage.removeItem('smt_card_order');
  }

  // ── Ordered institution list ───────────────────────────────────
  const orderedInsts = useMemo(() => {
    if (!institutions.length) return [];
    if (!cardOrder) {
      // Default: AUM descending (uses cached aumMap so order is stable)
      return [...institutions].sort((a, b) => (aumMap[b.id] || 0) - (aumMap[a.id] || 0));
    }
    // Custom order from localStorage; any new institution goes to the end
    const orderMap = Object.fromEntries(cardOrder.map((id, i) => [id, i]));
    return [...institutions].sort(
      (a, b) => (orderMap[a.id] ?? 9999) - (orderMap[b.id] ?? 9999)
    );
  }, [institutions, cardOrder, aumMap]);

  orderedInstsRef.current = orderedInsts; // keep closure ref current

  return { cardOrder, setCardOrder, aumMap, handleAumLoaded, orderedInsts, orderedInstsRef, resetOrder };
}
