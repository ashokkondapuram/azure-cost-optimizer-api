import React from 'react';
import { Link } from 'react-router-dom';
import AdvisorCategoryIcon from './AdvisorCategoryIcon';
import FindingCategoryIcon from './FindingCategoryIcon';
import { toDisplayText } from '../../utils/formatDisplay';
import {
  advisorCategoriesForTable,
  advisorCategoryLabel,
  advisorImpactTone,
} from '../../utils/advisorUtils';
import {
  findingCategoriesForTable,
  findingCategoryLabel,
  findingSeverityTone,
} from '../../utils/findingTableUtils';

function advisorIconTitle(recommendation) {
  const label = advisorCategoryLabel(recommendation.category);
  const parts = ['Azure Advisor', label];
  if (recommendation.impact) parts.push(recommendation.impact);
  if (recommendation.summary) parts.push(toDisplayText(recommendation.summary));
  return parts.join(' · ');
}

function findingIconTitle(finding) {
  const label = findingCategoryLabel(finding.category);
  const parts = ['Recommendation engine', label];
  if (finding.severity) parts.push(finding.severity);
  if (finding.rule_name) parts.push(finding.rule_name);
  else if (finding.detail || finding.recommendation) {
    parts.push(toDisplayText(finding.detail || finding.recommendation));
  }
  return parts.join(' · ');
}

export default function AdvisorTableCell({
  recommendations = [],
  findings = [],
  indexReady = true,
  findingsIndexReady = true,
  isError = false,
  subscriptionHasAdvisor = false,
  subscriptionHasFindings = false,
}) {
  const advisorIcons = indexReady && !isError ? advisorCategoriesForTable(recommendations) : [];
  const engineIcons = findingsIndexReady ? findingCategoriesForTable(findings) : [];
  const waiting = (!indexReady || !findingsIndexReady) && !advisorIcons.length && !engineIcons.length;

  if (waiting) {
    return <span className="resource-table__empty" title="Loading recommendations">…</span>;
  }
  if (isError && !engineIcons.length && !advisorIcons.length) {
    return (
      <span className="resource-table__empty resource-table__empty--warn" title="Could not load recommendations">
        !
      </span>
    );
  }

  if (!advisorIcons.length && !engineIcons.length) {
    if (subscriptionHasAdvisor || subscriptionHasFindings) {
      return <span className="resource-table__empty" title="No recommendations for this resource">—</span>;
    }
    return (
      <Link
        to="/admin/optimization"
        className="advisor-table-cell advisor-table-cell--sync-hint text-sm"
        title="Sync Azure Advisor and run analysis from Optimization center"
        onClick={(e) => e.stopPropagation()}
      >
        Sync
      </Link>
    );
  }

  return (
    <span className="advisor-table-cell">
      {advisorIcons.map((recommendation) => {
        const tone = advisorImpactTone(recommendation.impact);
        const label = advisorCategoryLabel(recommendation.category);
        return (
          <span
            key={`advisor:${recommendation.category}`}
            className={`advisor-table-cell__icon advisor-table-cell__icon--${tone} advisor-table-cell__icon--advisor`}
            title={advisorIconTitle(recommendation)}
          >
            <AdvisorCategoryIcon category={recommendation.category} size={12} />
            <span className="sr-only">{label}</span>
          </span>
        );
      })}
      {engineIcons.map((finding) => {
        const tone = findingSeverityTone(finding.severity);
        const label = findingCategoryLabel(finding.category);
        return (
          <span
            key={`engine:${finding.category}`}
            className={`advisor-table-cell__icon advisor-table-cell__icon--${tone} advisor-table-cell__icon--engine`}
            title={findingIconTitle(finding)}
          >
            <FindingCategoryIcon category={finding.category} size={12} />
            <span className="sr-only">{label}</span>
          </span>
        );
      })}
    </span>
  );
}
