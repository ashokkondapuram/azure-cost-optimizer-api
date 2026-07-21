import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import DashboardSummary from './DashboardSummary';
import WizSourceBreakdown from '../wiz/WizSourceBreakdown';
import WizInsightsChartGrid from '../wiz/charts/WizInsightsChartGrid';
import { EmptyState } from '../QueryStates';
import { PAGE_ICONS } from '../../config/assetIcons';
import {
  openFindingsCount,
  totalEstimatedSavings,
} from '../../utils/findingsSummaryUtils';

function FindingsSkeleton() {
  return (
    <section className="dashboard-section dashboard-section--findings" aria-busy="true">
      <div className="dashboard-kpi-skeleton dashboard-kpi-skeleton--sm skeleton" />
      <div className="dashboard-kpi-skeleton dashboard-kpi-skeleton--panel skeleton" />
    </section>
  );
}

/**
 * Subscription findings summary and optimization charts for the dashboard.
 * Action-centre-specific breakdowns live here instead of duplicating Cost explorer.
 */
export default function DashboardFindingsInsights({
  summary,
  portal,
  currency,
  isLoading,
}) {
  if (isLoading && !summary) {
    return <FindingsSkeleton />;
  }

  if (!summary) {
    return (
      <EmptyState
        iconKey={PAGE_ICONS.recommendations}
        message="No findings summary yet. Run analysis from the Action centre after syncing resources."
      />
    );
  }

  const kpisById = Object.fromEntries((portal?.kpis || []).map((k) => [k.id, k]));
  const inventoryTotal = Number(kpisById.total_resources?.value ?? 0);
  const openFindings = openFindingsCount(summary);
  const estSavings = totalEstimatedSavings(summary);
  const criticalCount = summary?.by_severity?.CRITICAL ?? summary?.severity?.CRITICAL ?? 0;
  const highCount = summary?.by_severity?.HIGH ?? summary?.severity?.HIGH ?? 0;

  return (
    <>
      <section
        id="findings-insights"
        className="dashboard-section dashboard-section--findings dashboard-section--enter"
        aria-label="Findings summary"
      >
        <header className="dashboard-section__header dashboard-section__header--bar">
          <h3 className="dashboard-section__title dashboard-section__title--bar">Findings summary</h3>
          <Link to="/action-centre?hasAction=1" className="btn btn-ghost btn-sm">
            View actions
            <ArrowRight size={14} />
          </Link>
        </header>

        <DashboardSummary
          inventoryTotal={inventoryTotal}
          openFindings={openFindings}
          estSavings={estSavings}
          criticalCount={criticalCount}
          highCount={highCount}
          currency={currency}
        />

        <WizSourceBreakdown summary={summary} />
      </section>

      {openFindings > 0 && (
        <section
          className="dashboard-section dashboard-section--charts dashboard-section--enter"
          aria-label="Optimization insights charts"
        >
          <header className="dashboard-section__header dashboard-section__header--bar">
            <h3 className="dashboard-section__title dashboard-section__title--bar">
              Optimization insights
            </h3>
          </header>
          <WizInsightsChartGrid summary={summary} currency={currency} compact />
        </section>
      )}
    </>
  );
}
