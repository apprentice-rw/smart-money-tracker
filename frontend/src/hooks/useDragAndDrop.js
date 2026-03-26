import { useState, useRef } from 'react';

export function useDragAndDrop(orderedInstsRef, setCardOrder) {
  const [draggingId, setDraggingId] = useState(null);
  const [dragOverId, setDragOverId] = useState(null);
  const ghostRef = useRef(null);

  function handleHandleMouseDown(e, instId) {
    if (e.button !== 0) return;
    e.preventDefault();

    document.body.style.cursor     = 'grabbing';
    document.body.style.userSelect = 'none';

    // ── Floating ghost ──────────────────────────────────────────
    const inst  = orderedInstsRef.current.find(i => i.id === instId);
    const ghost = document.createElement('div');
    ghost.className = 'smt-ghost';
    ghost.style.cssText = [
      'position:fixed',
      'pointer-events:none',
      'z-index:9999',
      'background:white',
      'border:1px solid #e5e7eb',
      'border-radius:16px',
      'padding:12px 20px',
      'box-shadow:0 24px 48px rgba(0,0,0,0.18),0 6px 16px rgba(0,0,0,0.10)',
      'min-width:180px',
      'max-width:300px',
      'font-family:-apple-system,BlinkMacSystemFont,"Inter","Segoe UI",sans-serif',
      'left:' + (e.clientX + 16) + 'px',
      'top:'  + (e.clientY + 16) + 'px',
    ].join(';');

    const row = document.createElement('div');
    row.style.cssText = 'display:flex;align-items:center;gap:8px';
    const hIcon = document.createElement('span');
    hIcon.textContent = '⠿';
    hIcon.style.cssText = 'color:#9ca3af;font-size:18px;flex-shrink:0';
    const hName = document.createElement('span');
    hName.textContent = inst ? (inst.display_name || inst.name) : '';
    hName.style.cssText = 'font-size:14px;font-weight:700;color:#111827;'
      + 'overflow:hidden;text-overflow:ellipsis;white-space:nowrap';
    row.appendChild(hIcon);
    row.appendChild(hName);
    ghost.appendChild(row);
    document.body.appendChild(ghost);
    ghostRef.current = ghost;

    setDraggingId(instId);

    // ── Mouse tracking ──────────────────────────────────────────
    let lastRawId = null;

    function onMouseMove(ev) {
      ghost.style.left = (ev.clientX + 16) + 'px';
      ghost.style.top  = (ev.clientY + 16) + 'px';

      const el    = document.elementFromPoint(ev.clientX, ev.clientY);
      const card  = el && el.closest('[data-institution-id]');
      const rawId = card ? card.dataset.institutionId : null;
      // Ignore hits on the card being dragged
      const eid   = (rawId !== null && rawId !== String(instId)) ? rawId : null;
      if (eid === lastRawId) return;
      lastRawId = eid;
      const target = eid
        ? orderedInstsRef.current.find(i => String(i.id) === eid)
        : null;
      setDragOverId(target ? target.id : null);
    }

    function onMouseUp(ev) {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup',   onMouseUp);
      ghost.remove();
      ghostRef.current           = null;
      document.body.style.cursor     = '';
      document.body.style.userSelect = '';

      const el    = document.elementFromPoint(ev.clientX, ev.clientY);
      const card  = el && el.closest('[data-institution-id]');
      const rawId = card ? card.dataset.institutionId : null;
      const tgt   = (rawId !== null && rawId !== String(instId))
        ? orderedInstsRef.current.find(i => String(i.id) === rawId)
        : null;

      if (tgt) {
        const ids  = orderedInstsRef.current.map(i => i.id);
        const from = ids.indexOf(instId);
        const to   = ids.indexOf(tgt.id);
        if (from !== -1 && to !== -1) {
          const next = [...ids];
          next.splice(from, 1);
          next.splice(from < to ? to - 1 : to, 0, instId);
          setCardOrder(next);
          localStorage.setItem('smt_card_order', JSON.stringify(next));
        }
      }

      setDraggingId(null);
      setDragOverId(null);
    }

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup',   onMouseUp);
  }

  return { draggingId, dragOverId, handleHandleMouseDown };
}
