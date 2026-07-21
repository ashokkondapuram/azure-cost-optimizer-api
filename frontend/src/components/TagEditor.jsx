import React, { useMemo, useState } from 'react';
import { Tag, Plus, Trash2 } from 'lucide-react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { patchResourceTags } from '../api/azure';
import AdminOnly from './AdminOnly';

function tagsToRows(tags) {
  const entries = Object.entries(tags || {});
  if (!entries.length) return [{ key: '', value: '' }];
  return entries.map(([key, value]) => ({ key, value: String(value) }));
}

function rowsToTags(rows) {
  const out = {};
  for (const row of rows) {
    const key = row.key.trim();
    if (!key) continue;
    out[key] = row.value.trim();
  }
  return out;
}

export default function TagEditor({
  resourceId,
  subscriptionId,
  tags = {},
  onUpdated,
}) {
  const queryClient = useQueryClient();
  const [rows, setRows] = useState(() => tagsToRows(tags));
  const [error, setError] = useState('');

  const dirty = useMemo(() => {
    const current = JSON.stringify(rowsToTags(rows));
    const original = JSON.stringify(tags || {});
    return current !== original;
  }, [rows, tags]);

  const mutation = useMutation({
    mutationFn: (nextTags) => patchResourceTags({
      subscription_id: subscriptionId,
      resource_id: resourceId,
      tags: nextTags,
    }),
    onSuccess: (data) => {
      setError('');
      setRows(tagsToRows(data.tags || {}));
      onUpdated?.(data.tags || {});
      queryClient.invalidateQueries({ predicate: (q) => Array.isArray(q.queryKey)
        && typeof q.queryKey[0] === 'string'
        && q.queryKey[0].startsWith('/resources') });
    },
    onError: (err) => {
      setError(err.normalizedMessage || err.message || 'Could not update tags.');
    },
  });

  const updateRow = (index, field, value) => {
    setRows((prev) => prev.map((row, i) => (i === index ? { ...row, [field]: value } : row)));
  };

  const addRow = () => setRows((prev) => [...prev, { key: '', value: '' }]);
  const removeRow = (index) => setRows((prev) => prev.filter((_, i) => i !== index));

  if (!resourceId || !subscriptionId) return null;

  return (
    <AdminOnly fallback={(
      <div className="tag-editor tag-editor--readonly">
        <h4 className="tag-editor__title"><Tag size={14} aria-hidden /> Tags</h4>
        {Object.keys(tags || {}).length === 0 ? (
          <p className="tag-editor__empty">No tags</p>
        ) : (
          <dl className="tag-editor__list">
            {Object.entries(tags).map(([key, value]) => (
              <div key={key} className="tag-editor__pair">
                <dt>{key}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
        )}
      </div>
    )}
    >
      <div className="tag-editor">
        <h4 className="tag-editor__title"><Tag size={14} aria-hidden /> Tags</h4>
        <div className="tag-editor__rows">
          {rows.map((row, index) => (
            <div key={index} className="tag-editor__row">
              <input
                type="text"
                value={row.key}
                onChange={(e) => updateRow(index, 'key', e.target.value)}
                placeholder="Key"
                aria-label={`Tag key ${index + 1}`}
              />
              <input
                type="text"
                value={row.value}
                onChange={(e) => updateRow(index, 'value', e.target.value)}
                placeholder="Value"
                aria-label={`Tag value ${index + 1}`}
              />
              <button
                type="button"
                className="btn btn-ghost btn-icon-only"
                onClick={() => removeRow(index)}
                aria-label="Remove tag"
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
        <div className="tag-editor__actions">
          <button type="button" className="btn btn-ghost btn-sm" onClick={addRow}>
            <Plus size={13} /> Add tag
          </button>
          <button
            type="button"
            className="btn btn-primary btn-sm"
            disabled={!dirty || mutation.isPending}
            onClick={() => mutation.mutate(rowsToTags(rows))}
          >
            {mutation.isPending ? 'Saving…' : 'Save tags'}
          </button>
        </div>
        {error && <p className="tag-editor__error" role="alert">{error}</p>}
      </div>
    </AdminOnly>
  );
}
