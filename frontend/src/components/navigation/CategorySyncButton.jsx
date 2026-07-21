import React, { useContext } from 'react';
import { CloudDownload } from 'lucide-react';
import { AppCtx } from '../../App';
import useResourceSync from '../../hooks/useResourceSync';

/**
 * Admin-only scoped sync for a nav or dashboard category.
 * variant: prominent = empty state CTA, compact = footer, header = inline beside nav group label.
 */
export default function CategorySyncButton({
  label,
  syncTypes,
  variant = 'prominent',
}) {
  const { subscription } = useContext(AppCtx);

  const { sync, syncing } = useResourceSync({
    subscription,
    syncTypes,
    progressLabel: `Syncing ${label}`,
    includeCosts: false,
    invalidateKeys: [
      ['resource-counts', subscription],
      ['findings-index', subscription],
      ['opt-overview', subscription],
    ],
  });

  if (!subscription || !syncTypes?.length) return null;

  const btnClass = {
    prominent: 'btn btn-primary btn-sm category-sync__btn',
    compact: 'btn btn-secondary btn-sm category-sync__btn category-sync__btn--compact',
    header: 'category-sync__btn category-sync__btn--header',
  }[variant] || 'btn btn-primary btn-sm category-sync__btn';

  const wrapClass = `category-sync${
    variant === 'compact' ? ' category-sync--compact' : ''
  }${variant === 'header' ? ' category-sync--header' : ''}`;

  const handleClick = (event) => {
    event.stopPropagation();
    sync().catch(() => {});
  };

  return (
    <div className={wrapClass}>
      <button
        type="button"
        className={btnClass}
        onClick={handleClick}
        disabled={syncing}
        aria-busy={syncing}
        title={`Sync ${label} from Azure`}
        aria-label={`Sync ${label} from Azure`}
      >
        {syncing ? (
          <div className="spin" aria-hidden />
        ) : (
          <CloudDownload size={14} strokeWidth={2.25} aria-hidden />
        )}
        {variant !== 'header' && (syncing ? 'Syncing…' : 'Sync from Azure')}
      </button>
    </div>
  );
}
