import React from 'react';
import { BookmarkPlus, X } from 'lucide-react';

/** Saved filter preset chips (localStorage via useFilterPresets). */
export default function FilterPresetsBar({
  presets = [],
  onApply,
  onSave,
  onDelete,
}) {
  if (!presets.length && !onSave) return null;

  return (
    <div className="filter-presets">
      <div className="filter-presets__chips">
        {presets.map((preset) => (
          <span key={preset.id} className="filter-presets__chip">
            <button type="button" className="filter-presets__apply" onClick={() => onApply(preset)}>
              {preset.name}
            </button>
            <button
              type="button"
              className="filter-presets__remove"
              aria-label={`Remove preset ${preset.name}`}
              onClick={() => onDelete(preset.id)}
            >
              <X size={12} />
            </button>
          </span>
        ))}
      </div>
      {onSave && (
        <button type="button" className="btn btn-ghost btn-sm filter-presets__save" onClick={onSave}>
          <BookmarkPlus size={14} /> Save filters
        </button>
      )}
    </div>
  );
}
