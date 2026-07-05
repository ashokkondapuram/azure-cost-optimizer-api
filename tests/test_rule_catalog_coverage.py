"""Coverage tests for expanded rule catalog and per-resource rule mappings."""

from app.optimizer.rule_catalog import (
    CANONICAL_RESOURCE_RULES,
    RULE_ALIASES,
    RULE_MANIFEST,
    canonical_resource_rule_catalog,
    list_all_rules,
    manifest_for_rule,
    resolve_rule_id,
)
from app.optimizer.rule_registry import ALL_KNOWN_RULE_IDS, is_known_rule, rule_engine_tier
from app.resources.registry import ALL_RESOURCE_MODULES


def test_every_canonical_resource_type_has_rules():
    for mod in ALL_RESOURCE_MODULES:
        canonical = getattr(mod, "CANONICAL_TYPE", None)
        assert canonical, f"{mod.__name__} missing CANONICAL_TYPE"
        assert canonical in CANONICAL_RESOURCE_RULES, canonical
        assert CANONICAL_RESOURCE_RULES[canonical], canonical


def test_canonical_resource_rules_are_cataloged():
    catalog_ids = {r["id"] for r in list_all_rules()}
    for canonical, rule_ids in CANONICAL_RESOURCE_RULES.items():
        for rule_id in rule_ids:
            resolved = resolve_rule_id(rule_id)
            assert resolved in RULE_MANIFEST or rule_id in RULE_MANIFEST, (
                f"{canonical}: {rule_id} -> {resolved} missing from RULE_MANIFEST"
            )
            assert rule_id in catalog_ids or resolved in catalog_ids, (
                f"{canonical}: {rule_id} missing from list_all_rules()"
            )


def test_rule_aliases_resolve_to_manifest_entries():
    for alias, canonical in RULE_ALIASES.items():
        assert canonical in RULE_MANIFEST, alias
        assert manifest_for_rule(alias), alias
        assert is_known_rule(alias)
        assert rule_engine_tier(alias) == rule_engine_tier(canonical)


def test_canonical_resource_rule_catalog_matches_registry():
    rows = canonical_resource_rule_catalog()
    assert len(rows) == len(CANONICAL_RESOURCE_RULES)
    for row in rows:
        assert row["rule_count"] == len(row["rule_ids"])
        assert row["canonical_type"] in CANONICAL_RESOURCE_RULES


def test_known_rule_ids_include_aliases():
    for alias in RULE_ALIASES:
        assert alias in ALL_KNOWN_RULE_IDS
