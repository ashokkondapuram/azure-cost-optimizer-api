"""Every optimization rule must have a declarative evidence spec."""

from app.rule_evidence_specs import RULE_EVIDENCE_SPECS, missing_specs


def test_every_manifest_rule_has_evidence_spec():
    missing = missing_specs()
    assert not missing, f"Rules missing evidence specs: {missing}"


def test_cost_export_rules_registered():
    cost_rules = [rid for rid in RULE_EVIDENCE_SPECS if rid.startswith("COST_") or rid in {
        "LOG_ANALYTICS_INGESTION", "APP_INSIGHTS_SAMPLING", "API_MANAGEMENT_SKU",
        "DATA_FACTORY_PIPELINE", "LOGIC_APP_RUN_HISTORY", "EVENT_HUBS_TIER",
        "SERVICE_BUS_TIER", "DATABRICKS_CLUSTER", "SYNAPSE_PAUSE", "ADX_INGESTION",
        "ML_WORKSPACE_COMPUTE", "BACKUP_RETENTION", "CDN_EGRESS", "FIREWALL_FIXED_COST",
        "COGNITIVE_SEARCH_SKU", "BANDWIDTH_REVIEW", "UNCLASSIFIED_SERVICE_SPEND",
    }]
    assert len(cost_rules) >= 18


def test_spec_includes_savings_methodology():
    from app.finding_evidence import build_rule_evidence

    out = build_rule_evidence(
        "VM_IDLE",
        {
            "avg_cpu_pct": 2.1,
            "cpu_threshold_pct": 5,
            "monthly_cost_usd": 200,
            "vm_size": "Standard_D2s_v3",
        },
        finding={"detail": "VM idle"},
        estimated_savings_usd=180.0,
    )
    assert out["checks"]
    assert out["savings_methodology"]["method"] == "factor_of_monthly_cost"
    assert out["savings_methodology"]["estimated_monthly_savings_usd"] == 180.0


def test_suggested_sku_expected_compares_to_current_sku():
    from app.finding_evidence import build_rule_evidence

    out = build_rule_evidence(
        "VM_SKU_SIZING_EXTENDED",
        {
            "avg_cpu_pct": 8.0,
            "avg_memory_pct": 12.0,
            "vm_size": "Standard_F16s_v2",
            "suggested_sku": "Standard_F8s_v2",
            "cpu_oversize_threshold_pct": 20,
            "mem_idle_pct": 30,
        },
        estimated_savings_usd=0.0,
    )
    sku_check = next(c for c in out["checks"] if c["signal"] == "Suggested SKU")
    assert sku_check["value"] == "Standard_F8s_v2"
    assert sku_check["threshold"] == "≠ Standard_F16s_v2"
    assert sku_check["passed"] is True


def test_not_empty_signals_have_meaningful_expected():
    from app.rule_evidence_specs import build_checks, RULE_EVIDENCE_SPECS

    spec = RULE_EVIDENCE_SPECS["VM_MISSING_GOVERNANCE_TAGS"]
    checks = build_checks(spec, {"missing_tags": ["Owner"]})
    tag_check = checks[0]
    assert tag_check["threshold"].lower() == "none"
    assert tag_check["passed"] is False

    env_spec = RULE_EVIDENCE_SPECS["SPOT_OPPORTUNITY"]
    env_checks = build_checks(env_spec, {"environment": "dev", "pricing_model": "PayAsYouGo"})
    env_check = next(c for c in env_checks if c["signal"] == "Environment tag")
    assert env_check["threshold"] == "Required tag present"


def test_cost_export_metadata_checks_have_present_criterion():
    from app.rule_evidence_specs import build_checks, cost_export_evidence_spec

    spec = cost_export_evidence_spec(
        "COGNITIVE_SEARCH_SKU",
        min_monthly_cost=50.0,
        savings_factor=0.1,
        component="search/cognitivesearch",
    )
    checks = build_checks(
        spec,
        {
            "resource_group": "AI-Initiatives",
            "location": "Canada East",
            "state": "Succeeded",
            "arm_resource_type": "Microsoft.Search/searchServices",
            "azure_service_name": "Azure Cognitive Search",
        },
    )
    by_signal = {c["signal"]: c for c in checks}
    assert by_signal["Resource group"]["threshold"] == "Present"
    assert by_signal["Location"]["threshold"] == "Present in inventory"
    assert by_signal["Provisioning / sync state"]["threshold"] == "Present in inventory"
    assert by_signal["ARM resource type"]["threshold"] == "Present"
    assert "Azure service" not in by_signal
