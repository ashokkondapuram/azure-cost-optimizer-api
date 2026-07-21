import React, { useMemo } from 'react';
import { formatCurrency } from '../../../utils/format';
import WizDonutChart from './WizDonutChart';
import WizBarChart from './WizBarChart';
import { SEVERITY_ORDER } from './wizChartColors';

export default function WizFilteredSavingsCharts({
  rows = [],
  currency = 'CAD',
  filteredSavings = 0,
}) {
  const { bySeverity, byService } = useMemo(() => {
    const sev = {};
    const svc = {};
    for (const { row, rec } of rows) {
      const savings = rec.savings || 0;
      if (savings <= 0) continue;
      const severity = rec.topFinding?.severity || 'INFO';
      sev[severity] = (sev[severity] || 0) + savings;
      const service = row.azureServiceName || 'Other';
      svc[service] = (svc[service] || 0) + savings;
    }
    return { bySeverity: sev, byService: svc };
  }, [rows]);

  const severityData = SEVERITY_ORDER
    .map((key) => ({ key, name: key, value: bySeverity[key] || 0 }))
    .filter((d) => d.value > 0);

  const serviceData = Object.entries(byService)
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 8);

  if (!filteredSavings && !severityData.length) return null;

  return (
    <section className="wiz-chart-grid wiz-chart-grid--panel" aria-label="Filtered savings charts">
      <WizDonutChart
        title="Savings by severity"
        subtitle="Recoverable savings in current view"
        data={severityData}
        centerValue={formatCurrency(filteredSavings, { currency, decimals: 0 })}
        centerLabel="/mo in view"
        valueMode="currency"
        currency={currency}
        height={185}
      />
      <WizBarChart
        title="Savings by service"
        subtitle="Top services in filtered results"
        data={serviceData}
        currency={currency}
        valueMode="currency"
        height={185}
      />
    </section>
  );
}
