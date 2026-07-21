/** @jest-environment node */
import {
  pickPrimaryCosmosFinding,
  pickPrimaryCosmosFindings,
  isCosmosResource,
} from './cosmosPrimaryFinding';

describe('cosmosPrimaryFinding', () => {
  const cosmosResource = {
    type: 'Microsoft.DocumentDB/databaseAccounts',
    id: '/subscriptions/s/resourceGroups/rg/providers/Microsoft.DocumentDB/databaseAccounts/acct1',
  };

  it('detects cosmos resources', () => {
    expect(isCosmosResource(cosmosResource, '/resources/cosmosdb')).toBe(true);
    expect(isCosmosResource({ type: 'Microsoft.Compute/virtualMachines' }, '/resources/vms')).toBe(false);
  });

  it('picks hot partition over serverless downsize', () => {
    const findings = [
      { rule_id: 'COSMOS_SERVERLESS', severity: 'MEDIUM', estimated_savings_usd: 200 },
      { rule_id: 'COSMOS_HOT_CONTAINER_DETECTED', severity: 'HIGH', estimated_savings_usd: 50 },
    ];
    expect(pickPrimaryCosmosFinding(findings).rule_id).toBe('COSMOS_HOT_CONTAINER_DETECTED');
  });

  it('suppresses downsize when throttling is present', () => {
    const findings = [
      { rule_id: 'COSMOS_SERVERLESS', severity: 'MEDIUM', estimated_savings_usd: 300 },
      { rule_id: 'COSMOS_THROTTLING_DETECTED', severity: 'HIGH', estimated_savings_usd: 0 },
    ];
    expect(pickPrimaryCosmosFinding(findings).rule_id).toBe('COSMOS_THROTTLING_DETECTED');
  });

  it('keeps highest-savings throughput option when no stress signals', () => {
    const findings = [
      { rule_id: 'COSMOS_AUTOSCALE_EXTENDED', severity: 'MEDIUM', estimated_savings_usd: 80 },
      { rule_id: 'COSMOS_SERVERLESS', severity: 'MEDIUM', estimated_savings_usd: 150 },
    ];
    expect(pickPrimaryCosmosFinding(findings).rule_id).toBe('COSMOS_SERVERLESS');
  });

  it('returns single primary for cosmos resource lists', () => {
    const findings = [
      { rule_id: 'COSMOS_SERVERLESS', severity: 'MEDIUM', estimated_savings_usd: 100 },
      { rule_id: 'COSMOS_INDEXING_OVERPROVISIONED', severity: 'LOW', estimated_savings_usd: 40 },
    ];
    const primary = pickPrimaryCosmosFindings(findings, cosmosResource, '/resources/cosmosdb');
    expect(primary).toHaveLength(1);
    expect(primary[0].evidence.primary_recommendation).toBe(true);
  });

  it('passes through non-cosmos resources unchanged', () => {
    const findings = [
      { rule_id: 'VM_OVERSIZE', severity: 'HIGH', estimated_savings_usd: 100 },
      { rule_id: 'VM_UNDERUTILIZED', severity: 'MEDIUM', estimated_savings_usd: 50 },
    ];
    expect(pickPrimaryCosmosFindings(findings, { type: 'Microsoft.Compute/virtualMachines' }, '/resources/vms'))
      .toHaveLength(2);
  });
});
