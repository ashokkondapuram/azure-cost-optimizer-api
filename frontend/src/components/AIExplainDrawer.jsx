import React, { useState } from 'react';
import { X, Sparkles, Loader2, AlertTriangle, ChevronRight, Copy, Check } from 'lucide-react';

const MOCK_EXPLAIN = (resource, findingType) => ({
  why: `This resource (${resource}) has been flagged because its average CPU utilisation has been below 5% for the past 14 days, indicating that its current SKU is significantly over-provisioned for actual workload demand.`,
  impact_act: `Applying the recommended right-sizing action could reduce monthly compute costs by an estimated 35–45%. The change involves a live VM resize which typically takes 2–5 minutes with a brief service interruption.`,
  impact_ignore: `If left unchanged, the resource will continue to incur excess spend. Over a 12-month period this could amount to CAD 3,840 in preventable costs.`,
  how_to: `1. Navigate to the resource in Azure Portal.\n2. Stop the VM (deallocate).\n3. Change the size to the recommended SKU.\n4. Restart the VM and verify application health.\nAlternatively, use the Approve action in this app to automate the change.`,
  confidence: 92,
});

export default function AIExplainDrawer({ open, onClose, resource, findingType, title }) {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [copied, setCopied] = useState(false);

  React.useEffect(() => {
    if (open && !data) {
      setLoading(true);
      setTimeout(() => {
        setData(MOCK_EXPLAIN(resource, findingType));
        setLoading(false);
      }, 1200);
    }
    if (!open) setData(null);
  }, [open, resource, findingType]);

  const copyExplanation = () => {
    if (!data) return;
    navigator.clipboard?.writeText(`${data.why}\n\nImpact (act): ${data.impact_act}\n\nImpact (ignore): ${data.impact_ignore}\n\nHow to fix:\n${data.how_to}`);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className={`ai-explain-drawer${open ? ' ai-explain-drawer--open' : ''}`}>
      <div className="ai-explain-drawer__backdrop" onClick={onClose} aria-hidden />
      <div className="ai-explain-drawer__panel" role="dialog" aria-modal="true" aria-labelledby="ai-explain-title">
        <div className="ai-explain-drawer__accent" aria-hidden />
        <div className="ai-explain-drawer__head">
          <div>
            <h2 id="ai-explain-title" className="ai-explain-drawer__title text-title-medium">
              <Sparkles size={16} className="ai-explain-drawer__title-icon" aria-hidden />
              AI explanation
            </h2>
            {title && <p className="ai-explain-drawer__subtitle text-caption">{title}</p>}
          </div>
          <div className="ai-explain-drawer__actions">
            {data && (
              <button
                type="button"
                className="btn btn-ghost btn-sm btn-icon-only"
                onClick={copyExplanation}
                title="Copy"
                aria-label="Copy explanation"
              >
                {copied ? <Check size={14} /> : <Copy size={14} />}
              </button>
            )}
            <button
              type="button"
              className="btn btn-ghost btn-sm btn-icon-only"
              onClick={onClose}
              title="Close"
              aria-label="Close"
            >
              <X size={14} />
            </button>
          </div>
        </div>

        <div className="ai-explain-drawer__body">
          {loading && (
            <div className="ai-explain-loading text-body-medium">
              <Loader2 size={24} className="ai-spin" aria-hidden />
              <span>Analysing with AI…</span>
            </div>
          )}

          {!loading && data && (
            <>
              <div className="ai-confidence card card--flat">
                <span className="ai-confidence__label text-label">AI confidence</span>
                <div className="ai-confidence__bar">
                  <div className="ai-confidence__fill" style={{ width: `${data.confidence}%` }} />
                </div>
                <span className="ai-confidence__value">{data.confidence}%</span>
              </div>

              <div className="ai-section card card--ai">
                <div className="ai-section__head text-label">
                  <ChevronRight size={13} aria-hidden />
                  Why is this flagged?
                </div>
                <p className="ai-section__body text-body-medium">{data.why}</p>
              </div>

              <div className="ai-section card card--ai card--ai-act">
                <div className="ai-section__head text-label">
                  <ChevronRight size={13} aria-hidden />
                  Impact if you act
                </div>
                <p className="ai-section__body text-body-medium">{data.impact_act}</p>
              </div>

              <div className="ai-section card card--ai card--ai-ignore">
                <div className="ai-section__head text-label">
                  <AlertTriangle size={13} aria-hidden />
                  Impact if ignored
                </div>
                <p className="ai-section__body text-body-medium">{data.impact_ignore}</p>
              </div>

              <div className="ai-section card card--ai">
                <div className="ai-section__head text-label">
                  <ChevronRight size={13} aria-hidden />
                  How to fix
                </div>
                <pre className="ai-section__code">{data.how_to}</pre>
              </div>

              <p className="ai-disclaimer text-caption">AI-generated explanation. Verify before taking action.</p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
