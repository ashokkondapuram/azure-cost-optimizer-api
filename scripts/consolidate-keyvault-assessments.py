#!/usr/bin/env python3
"""Consolidate Key Vault child assessment JSON files into keyvault-assessment.json."""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

CHILD_TYPES = {
    "Microsoft.KeyVault/vaults/keys": "keyvault-key-assessment.json",
    "Microsoft.KeyVault/vaults/secrets": "keyvault-secret-assessment.json",
    "Microsoft.KeyVault/vaults/certificates": "keyvault-certificate-assessment.json",
}

VAULT_FILE = DATA / "keyvault-assessment.json"
INDEX_FILE = DATA / "assessment-index.json"
MATRIX_FILE = DATA / "assessment-case-matrix.json"

SKIP_RULE_PREFIXES = ("uami_", "cost_", "property_", "tag_")


def load_json(path: pathlib.Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_child_from_git(filename: str) -> dict | None:
    try:
        raw = subprocess.check_output(
            ["git", "show", f"HEAD:data/{filename}"],
            cwd=ROOT,
            text=True,
        )
        return json.loads(raw)
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        path = DATA / filename
        if path.exists():
            return load_json(path)
        return None


def save_json(path: pathlib.Path, data: dict) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")


def _is_child_specific(rule_id: str, arm_suffix: str) -> bool:
    if not rule_id or rule_id.startswith(SKIP_RULE_PREFIXES):
        return False
    if rule_id.startswith("metric_"):
        token = arm_suffix.lower()
        if token in rule_id.lower():
            return True
        generic = (
            "operationcount",
            "daystoexpiry",
            "rotationoverdue",
            "unuseddays",
            "tokenrequests",
        )
        return any(g in rule_id.lower() for g in generic)
    return rule_id.startswith("kv_")


def normalize_rule_for_recommendation(rule: dict) -> dict:
    """Ensure merged child rules satisfy recommendationRules validator shape."""
    out = dict(rule)
    condition = dict(out.get("condition") or {})
    conditions = list(condition.get("conditions") or [])
    if conditions:
        paths = []
        parts = []
        for cond in conditions:
            field = cond.get("field") or cond.get("path") or ""
            if field:
                paths.append(field)
            op = cond.get("operator")
            if op in {"missing", "present"} and "value" not in cond:
                cond["value"] = True
            val = cond.get("value")
            if op == "missing":
                parts.append(f"get_value(resource, '{field}') missing True")
            elif op == "present":
                parts.append(f"get_value(resource, '{field}') present")
            else:
                parts.append(f"get_value(resource, '{field}') {op} {val!r}")
        joiner = " and " if condition.get("type", "all") == "all" else " or "
        condition.setdefault("evaluator", "field_operator_value")
        condition.setdefault("pythonCompatible", True)
        condition.setdefault("aiCompatible", True)
        condition.setdefault("pythonExpression", joiner.join(parts) or f"rule_{out.get('id')}")
        condition.setdefault("requiredSignalPaths", paths or [f"metrics.{out.get('id')}"])
        condition.setdefault("type", "all")
        condition["conditions"] = conditions
    out["condition"] = condition
    out["manualAssessmentAllowed"] = False
    out["aiAssessmentAllowed"] = False
    out["pythonCompatible"] = True
    out["aiCompatible"] = True
    out.setdefault("conditionFormat", "path_operator_value_group")
    out.setdefault("backendCompatible", True)
    out.setdefault("dbBacked", True)
    out.setdefault("runtimeExecutable", True)
    out.setdefault("pillar", out.get("pillar") or "cost")
    out.setdefault("severity", out.get("severity") or "medium")
    action = (
        out.get("recommendationAction")
        or out.get("actionOutcome")
        or (out.get("output") or {}).get("recommendationAction")
        or "investigate"
    )
    out.setdefault("recommendationAction", action)
    out.setdefault("actionOutcome", action)
    if not out.get("recommendation"):
        output = out.get("output") or {}
        out["recommendation"] = (
            output.get("recommendedActionText")
            or output.get("shortMessage")
            or output.get("message")
            or out.get("id")
        )
    return out


def extract_child_rules(child_data: dict, arm_type: str) -> list[dict]:
    suffix = arm_type.split("/")[-1]
    rules: list[dict] = []
    seen: set[str] = set()

    for section in ("metricAssessmentRules", "recommendationRules", "assessmentRules"):
        for rule in child_data.get(section) or []:
            rule_id = str(rule.get("id") or "")
            if not _is_child_specific(rule_id, suffix):
                continue
            if rule_id in seen:
                continue
            seen.add(rule_id)
            merged = dict(rule)
            merged["appliesToResourceTypes"] = [arm_type]
            merged["resourceScope"] = "child"
            merged = normalize_rule_for_recommendation(merged)
            rules.append(merged)
    return rules


def main() -> int:
    vault = load_json(VAULT_FILE)
    vault["recommendationRules"] = [
        r for r in (vault.get("recommendationRules") or [])
        if not r.get("appliesToResourceTypes") and r.get("resourceScope") != "child"
    ]
    existing_ids = {str(r.get("id")) for r in vault.get("recommendationRules") or []}
    added = 0

    for arm_type, filename in CHILD_TYPES.items():
        child = load_child_from_git(filename)
        if not child:
            print(f"skip missing {filename}")
            continue
        for rule in extract_child_rules(child, arm_type):
            rule_id = str(rule.get("id"))
            if rule_id in existing_ids:
                rule["id"] = f"kv_{arm_type.split('/')[-1]}_{rule_id}"
            existing_ids.add(str(rule["id"]))
            vault.setdefault("recommendationRules", []).append(rule)
            added += 1

    contract = vault.setdefault("assessmentContract", {})
    contract["consolidatedChildResourceTypes"] = list(CHILD_TYPES.keys())

    save_json(VAULT_FILE, vault)

    index = load_json(INDEX_FILE)
    for item in index.get("items") or []:
        if item.get("resourceType") in CHILD_TYPES:
            item["assessmentFile"] = "keyvault-assessment.json"
            item["consolidatedInto"] = "Microsoft.KeyVault/vaults"
    remaining = [
        p for p in DATA.glob("*-assessment.json")
        if p.name != "assessment-case-matrix.json"
    ]
    index["totalAssessmentFiles"] = len(remaining)
    save_json(INDEX_FILE, index)

    if MATRIX_FILE.exists():
        matrix = load_json(MATRIX_FILE)
        for entry in matrix.get("resources") or []:
            if entry.get("assessmentFile") in set(CHILD_TYPES.values()):
                entry["assessmentFile"] = "keyvault-assessment.json"
        save_json(MATRIX_FILE, matrix)

    for filename in CHILD_TYPES.values():
        path = DATA / filename
        if path.exists():
            path.unlink()
            print(f"removed {filename}")

    print(f"consolidated {added} child rules into keyvault-assessment.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
