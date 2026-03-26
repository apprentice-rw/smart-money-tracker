import { useState } from 'react';

export function useCollapse() {
  const [collapsedMap, setCollapsedMap] = useState({});

  function toggleCollapse(id) {
    setCollapsedMap(prev => ({ ...prev, [id]: !prev[id] }));
  }

  function collapseAll(institutions) {
    const next = {};
    institutions.forEach(i => { next[i.id] = true; });
    setCollapsedMap(next);
  }

  function expandAll() {
    setCollapsedMap({});
  }

  return { collapsedMap, toggleCollapse, collapseAll, expandAll };
}
