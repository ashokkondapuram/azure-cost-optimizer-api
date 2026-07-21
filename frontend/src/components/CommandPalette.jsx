import React, {
  useCallback, useEffect, useMemo, useRef, useState,
} from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import {
  ArrowRight, Command, Search, Zap,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import {
  OVERVIEW_NAV,
  ADVANCED_NAV_GROUPS,
  OPTIMIZATION_NAV_ITEMS,
  RESOURCE_PAGES,
  SYSTEM_NAV,
  actionCentreTypeLink,
} from '../config/appRegistry';

function matchesQuery(query, text) {
  const q = String(query || '').trim().toLowerCase();
  if (!q) return true;
  return String(text || '').toLowerCase().includes(q);
}

function buildStaticItems(isAdmin) {
  const items = [];
  for (const nav of OVERVIEW_NAV) {
    items.push({ id: `page:${nav.path}`, label: nav.title, group: 'Pages', path: nav.path });
  }
  for (const group of ADVANCED_NAV_GROUPS) {
    for (const nav of group.items) {
      items.push({
        id: `page:${nav.path}`,
        label: nav.title,
        group: group.label,
        path: nav.path,
      });
    }
  }
  if (isAdmin) {
    for (const nav of OPTIMIZATION_NAV_ITEMS) {
      items.push({ id: `page:${nav.path}`, label: nav.title, group: 'System', path: nav.path });
    }
    for (const nav of SYSTEM_NAV) {
      items.push({ id: `page:${nav.path}`, label: nav.title, group: 'System', path: nav.path });
    }
  }
  for (const page of Object.values(RESOURCE_PAGES)) {
    if (page.hidden) continue;
    items.push({
      id: `resource-page:${page.id}`,
      label: page.title,
      group: 'Resources',
      path: actionCentreTypeLink(page.id),
    });
  }
  if (isAdmin) {
    items.push({
      id: 'action:sync',
      label: 'Open sync center',
      group: 'Actions',
      path: '/admin/optimization',
    });
  }
  return items;
}

function cachedResourceItems(queryClient, subscription) {
  const items = [];
  const queries = queryClient.getQueriesData({
    predicate: (q) => Array.isArray(q.queryKey)
      && typeof q.queryKey[0] === 'string'
      && q.queryKey[0].startsWith('/resources')
      && q.queryKey[1] === subscription,
  });
  const seen = new Set();
  for (const [, data] of queries) {
    const rows = data?.items || data?.data || data || [];
    if (!Array.isArray(rows)) continue;
    for (const row of rows.slice(0, 200)) {
      const id = (row.id || row.resource_id || '').toLowerCase();
      const name = row.name || row.resource_name;
      if (!id || !name || seen.has(id)) continue;
      seen.add(id);
      items.push({
        id: `resource:${id}`,
        label: name,
        subtitle: row.resourceGroup || row.resource_group,
        group: 'Inventory',
        path: '/action-centre',
        resourceId: id,
        search: name,
      });
    }
  }
  return items.filter((item) => matchesQuery('', item.label));
}

function cachedFindingItems(queryClient, subscription) {
  const items = [];
  const data = queryClient.getQueryData(['findings-index', subscription]);
  const rows = Array.isArray(data) ? data : [];
  const seen = new Set();
  for (const row of rows.slice(0, 300)) {
    const key = `${row.rule_id}:${row.resource_id}`;
    if (seen.has(key)) continue;
    seen.add(key);
    items.push({
      id: `finding:${row.id}`,
      label: row.rule_name || row.rule_id,
      subtitle: row.resource_name,
      group: 'Findings',
      path: '/action-centre',
      search: `${row.rule_name} ${row.resource_name}`,
    });
  }
  return items;
}

export default function CommandPalette({ subscription }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [activeIdx, setActiveIdx] = useState(0);
  const inputRef = useRef(null);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { isAdmin } = useAuth();

  const staticItems = useMemo(() => buildStaticItems(isAdmin), [isAdmin]);

  const allItems = useMemo(() => {
    const dynamic = subscription
      ? [...cachedResourceItems(queryClient, subscription), ...cachedFindingItems(queryClient, subscription)]
      : [];
    return [...staticItems, ...dynamic];
  }, [staticItems, queryClient, subscription]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return allItems.slice(0, 40);
    return allItems.filter((item) => matchesQuery(q, item.search || item.label)
      || matchesQuery(q, item.subtitle)).slice(0, 40);
  }, [allItems, query]);

  useEffect(() => {
    setActiveIdx(0);
  }, [query, open]);

  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen((v) => !v);
      }
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => {
    if (open) {
      setQuery('');
      window.setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [open]);

  const runItem = useCallback((item) => {
    setOpen(false);
    if (item.path) {
      if (item.resourceId) {
        navigate(`/action-centre?resource=${encodeURIComponent(item.resourceId)}`);
        return;
      }
      const url = item.search ? `${item.path}?search=${encodeURIComponent(item.search)}` : item.path;
      navigate(url);
    }
  }, [navigate]);

  const onKeyDown = (e) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIdx((i) => Math.min(i + 1, filtered.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIdx((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter' && filtered[activeIdx]) {
      e.preventDefault();
      runItem(filtered[activeIdx]);
    }
  };

  if (!open) return null;

  return (
    <>
      <div className="command-palette-backdrop" onClick={() => setOpen(false)} aria-hidden />
      <div className="command-palette card" role="dialog" aria-label="Command palette">
        <div className="command-palette__input-wrap">
          <Search size={16} aria-hidden />
          <input
            ref={inputRef}
            type="search"
            className="command-palette__input"
            placeholder="Search pages, resources, findings, actions…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            aria-autocomplete="list"
          />
          <kbd className="command-palette__hint"><Command size={11} />K</kbd>
        </div>
        <ul className="command-palette__results" role="listbox">
          {filtered.length === 0 && (
            <li className="command-palette__empty">No matches</li>
          )}
          {filtered.map((item, idx) => (
            <li key={item.id}>
              <button
                type="button"
                className={`command-palette__item${idx === activeIdx ? ' active' : ''}`}
                onClick={() => runItem(item)}
                role="option"
                aria-selected={idx === activeIdx}
              >
                <span className="command-palette__item-main">
                  <span>{item.label}</span>
                  {item.subtitle && <span className="command-palette__subtitle">{item.subtitle}</span>}
                </span>
                <span className="command-palette__meta">
                  {item.group}
                  {item.path && <ArrowRight size={12} />}
                  {item.id === 'action:sync' && <Zap size={12} />}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </>
  );
}
