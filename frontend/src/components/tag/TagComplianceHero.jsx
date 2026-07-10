import React from 'react';
import { Plus, X, Tag, Info } from 'lucide-react';
import PageHero from '../layout/PageHero';
import { toDisplayText } from '../../utils/formatDisplay';

function scoreTone(pct) {
  if (pct == null) return 'default';
  if (pct >= 90) return 'success';
  if (pct >= 70) return 'warning';
  return 'danger';
}

function TagCoverageStrip({ tagCoverage, tagMissingCounts, total, activeTag, onTagClick }) {
  if (!total || !tagCoverage) {
    return (
      <div className="tag-hero__coverage-strip tag-hero__coverage-strip--empty">
        <span>No tag coverage to chart yet</span>
      </div>
    );
  }

  return (
    <div className="tag-hero__coverage-legend">
      {Object.entries(tagCoverage).map(([tag, pct]) => (
        <button
          key={tag}
          type="button"
          className={`tag-hero__legend-item${activeTag === tag ? ' tag-hero__legend-item--active' : ''}`}
          onClick={() => onTagClick?.(tag)}
          title={`${tag}: ${pct}% present · ${(tagMissingCounts?.[tag] ?? 0).toLocaleString()} missing`}
        >
          <span className="tag-hero__legend-dot" style={{ background: pct >= 90 ? '#0d9488' : pct >= 70 ? '#f59e0b' : '#ef4444' }} />
          {tag} {pct}%
        </button>
      ))}
    </div>
  );
}

function RequiredTagsEditor({ tags, onChange }) {
  const [newTag, setNewTag] = React.useState('');

  return (
    <div className="tag-hero__required-tags">
      <span className="tag-hero__required-label">Required tags</span>
      <div className="tag-hero__required-chips">
        {tags.map((tag) => (
          <span key={tag} className="chip active">
            {tag}
            <button
              type="button"
              className="tag-hero__chip-remove"
              onClick={() => onChange(tags.filter((item) => item !== tag))}
              aria-label={`Remove ${tag}`}
            >
              <X size={11} />
            </button>
          </span>
        ))}
        <form
          className="tag-hero__add-tag"
          onSubmit={(e) => {
            e.preventDefault();
            const value = newTag.trim().toLowerCase();
            if (value && !tags.includes(value)) onChange([...tags, value]);
            setNewTag('');
          }}
        >
          <input
            type="text"
            value={newTag}
            onChange={(e) => setNewTag(e.target.value)}
            placeholder="Add tag"
            aria-label="Add required tag"
          />
          <button type="submit" aria-label="Add tag">
            <Plus size={13} />
          </button>
        </form>
      </div>
    </div>
  );
}

export default function TagComplianceHero({
  subscriptionLabel,
  data,
  loading,
  requiredTags,
  onRequiredTagsChange,
  activeMissingTag,
  onMissingTagClick,
}) {
  const total = data?.total_resources ?? 0;
  const score = data?.score_pct;
  const subtitle = [
    subscriptionLabel ? toDisplayText(subscriptionLabel) : null,
    total ? `${total.toLocaleString()} active resources scored` : 'No active resources',
    data?.required_tags?.length
      ? `required: ${data.required_tags.join(', ')}`
      : null,
  ].filter(Boolean).join(' · ');

  return (
    <PageHero
      variant="adv-tool-hero--tags tag-compliance-hero"
      eyebrow="Governance"
      title="Tag compliance"
      subtitle={subtitle}
      isLoading={loading && !data}
      metrics={[
        {
          label: 'Compliance score',
          value: score != null ? `${score}%` : '—',
          tone: scoreTone(score),
          featured: true,
          sub: score != null && score >= 90 ? 'On track' : 'Needs remediation',
        },
        {
          label: 'Total resources',
          value: total.toLocaleString(),
          tone: 'default',
        },
        {
          label: 'Fully compliant',
          value: (data?.fully_compliant ?? 0).toLocaleString(),
          tone: 'success',
        },
        {
          label: 'Non-compliant',
          value: (data?.non_compliant_count ?? 0).toLocaleString(),
          tone: 'danger',
        },
      ]}
      actions={[
        { id: 'gov', label: 'Governance dashboard', href: '/governance' },
        { id: 'settings', label: 'Settings', href: '/settings' },
      ]}
      footer={(
        <div className="tag-hero__footer">
          <RequiredTagsEditor tags={requiredTags} onChange={onRequiredTagsChange} />
          <div className="tag-hero__footer-block">
            <span className="tag-hero__footer-label">
              <Tag size={14} aria-hidden />
              Coverage per required tag — click to filter missing
            </span>
            <TagCoverageStrip
              tagCoverage={data?.tag_coverage_pct}
              tagMissingCounts={data?.tag_missing_counts}
              total={total}
              activeTag={activeMissingTag}
              onTagClick={onMissingTagClick}
            />
          </div>
        </div>
      )}
    />
  );
}

export function TagComplianceDataNote({ data }) {
  if (!data) return null;

  const notes = [
    'Scores use active inventory resources from the latest sync. Tag keys are matched case-insensitively against tags_json on each resource.',
  ];

  if (data.items_truncated) {
    notes.push(
      `The table lists ${(data.items_returned ?? 0).toLocaleString()} of ${(data.non_compliant_count ?? 0).toLocaleString()} non-compliant resources. Charts use full subscription totals.`,
    );
  }

  if (data.message) {
    notes.push(data.message);
  }

  return (
    <aside className="tag-data-note" aria-label="How tag compliance is calculated">
      <Info size={15} aria-hidden className="tag-data-note__icon" />
      <div className="tag-data-note__body">
        {notes.map((text) => (
          <p key={text}>{text}</p>
        ))}
      </div>
    </aside>
  );
}
