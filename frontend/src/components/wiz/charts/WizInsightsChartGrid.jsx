import React, { useMemo } from 'react';
import { formatCurrency } from '../../../utils/format';
import {
  openFindingsCount,
  totalEstimatedSavings,
  severityBreakdown,
  categoryBreakdown,
  sourceBreakdownOrdered,
} from '../../../utils/findingsSummaryUtils';
import WizDonutChart, { severityDonutData, categoryBarData, sourceBarData } from './WizDonutChart';
import WizBarChart from './WizBarChart';
import WizRadialGauge from './WizRadialGauge';

export default function WizInsightsChartGrid({
  summary,
  currency = 'CAD',
  compact = false,
}) {
  const bySeverity = severityBreakdown(summary);
  const byCategory = categoryBreakdown(summary);
  const sourceData = useMemo(() => sourceBarData(sourceBreakdownOrdered(summary)), [summary]);
  const openTotal = openFindingsCount(summary);
  const totalSavings = totalEstimatedSavings(summary);
  const costOpt = summary?.cost_optimization_findings ?? 0;
  const withSavings = summary?.with_savings_findings ?? 0;

  const severityData = useMemo(() => severityDonutData(bySeverity), [bySeverity]);
  const categoryData = useMemo(() => categoryBarData(byCategory, 8), [byCategory]);

  const actionablePct = openTotal > 0 ? Math.round((costOpt / openTotal) * 100) : 0;
  const savingsPct = openTotal > 0 ? Math.round((withSavings / openTotal) * 100) : 0;

  if (!openTotal && !totalSavings) return null;

  return (
    <section className={`wiz-chart-grid${compact ? ' wiz-chart-grid--compact' : ''}`} aria-label="Optimization insights charts">
      <WizDonutChart
        title="Issues by severity"
        subtitle="Open findings distribution"
        data={severityData}
        centerValue={openTotal.toLocaleString()}
        centerLabel="open"
        height={compact ? 170 : 200}
      />
      <WizRadialGauge
        title="Actionable coverage"
        subtitle="Cost optimization findings vs all open issues"
        value={actionablePct}
        max={100}
        label="of issues are actionable"
        fill="#0073ff"
        height={compact ? 160 : 180}
      />
      <WizRadialGauge
        title="Savings potential"
        subtitle={formatCurrency(totalSavings, { currency, decimals: 0 })}
        value={savingsPct}
        max={100}
        label="issues have quantified savings"
        fill="#22c55e"
        height={compact ? 160 : 180}
      />
      <WizBarChart
        title="Issues by source"
        subtitle="Engine, Advisor, and governance split"
        data={sourceData}
        dataKey="count"
        height={compact ? 190 : 220}
      />
      <WizBarChart
        title="Issues by category"
        subtitle="Finding count by service category"
        data={categoryData}
        dataKey="count"
        height={compact ? 190 : 220}
      />
    </section>
  );
}
