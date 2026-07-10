#!/usr/bin/env python3
import argparse
import json
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parent


def load_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def get_path(data, path):
    current = data
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def evaluate_condition(resource, condition):
    value = get_path(resource, condition["field"])
    operator = condition["operator"]
    expected = condition.get("value")

    if operator == "eq":
        return value == expected
    if operator == "neq":
        return value != expected
    if operator == "gt":
        return value is not None and value > expected
    if operator == "gte":
        return value is not None and value >= expected
    if operator == "lt":
        return value is not None and value < expected
    if operator == "lte":
        return value is not None and value <= expected
    if operator == "in":
        return value in expected
    if operator == "not_in":
        return value not in expected
    if operator == "contains":
        return value is not None and expected in value
    if operator == "missing":
        return value is None
    if operator == "present":
        return value is not None
    if operator == "is_true":
        return value is True
    if operator == "is_false":
        return value is False
    raise ValueError(f"Unsupported operator: {operator}")


def evaluate_condition_group(resource, group):
    results = [evaluate_condition(resource, condition) for condition in group.get("conditions", [])]
    if group.get("type") == "all":
        return all(results)
    if group.get("type") == "any":
        return any(results)
    raise ValueError(f"Unsupported condition group type: {group.get('type')}")


def classify_score(score, levels):
    for level in levels:
        low, high = level["scoreRange"]
        if low <= score <= high:
            return level["level"]
    return "unknown"


def assess_resource(assessment, resource):
    python_assessment = assessment["pythonAssessment"]
    scoring = python_assessment["defaultScoring"]
    score = scoring["startScore"]
    matched = []

    severity_for_level = {
        "worst": "critical",
        "bad": "high",
        "warning": "medium",
        "good": "low",
        "best": None
    }

    for level in ("worst", "bad", "warning"):
        for condition in python_assessment["deterministicCases"].get(level, []):
            if evaluate_condition(resource, condition):
                severity = severity_for_level[level]
                score -= scoring["deductions"].get(severity, 0)
                matched.append({
                    "level": level,
                    "condition": condition
                })

    caps = scoring.get("caps", {})
    if get_path(resource, "signals.anyCriticalSecurityFinding"):
        score = min(score, caps.get("anyCriticalSecurityFinding", score))
    if get_path(resource, "signals.anyHighSecurityFinding"):
        score = min(score, caps.get("anyHighSecurityFinding", score))
    if get_path(resource, "signals.anyHighReliabilityFinding"):
        score = min(score, caps.get("anyHighReliabilityFinding", score))
    if get_path(resource, "signals.missingRequiredMetrics"):
        score = min(score, caps.get("missingRequiredMetrics", score))
    if get_path(resource, "signals.missingCostData"):
        score = min(score, caps.get("missingCostData", score))
    if get_path(resource, "signals.unknownProductionOwner"):
        score = min(score, caps.get("unknownProductionOwner", score))

    score = max(0, min(100, score))
    best_conditions = python_assessment["deterministicCases"].get("best", [])
    best_matched = best_conditions and all(evaluate_condition(resource, c) for c in best_conditions)
    classification = classify_score(score, python_assessment["classificationLevels"])
    if best_matched and not matched:
        classification = "best"
        score = max(score, 90)

    matched_rules = []
    for rule in assessment.get("recommendationRules", []):
        if evaluate_condition_group(resource, rule["condition"]):
            matched_rules.append({
                "id": rule["id"],
                "pillar": rule["pillar"],
                "severity": rule["severity"],
                "recommendation": rule["recommendation"],
                "confidence": rule.get("confidence"),
                "condition": rule["condition"]
            })

    return {
        "resource_id": resource.get("resource_id"),
        "resource_type": resource.get("resource_type"),
        "assessment_file": assessment.get("_file"),
        "score": score,
        "classification": classification,
        "matchedConditions": matched,
        "matchedRecommendationRules": matched_rules,
        "bestConditionsMatched": bool(best_matched)
    }


def load_assessments():
    assessments = {}
    for path in ROOT.glob("*-assessment.json"):
        data = load_json(path)
        data["_file"] = path.name
        assessments[data["resourceType"]] = data
    return assessments


def main():
    parser = argparse.ArgumentParser(description="Deterministic Azure assessment runtime")
    parser.add_argument("input", help="Normalized resource JSON object or list")
    args = parser.parse_args()

    assessments = load_assessments()
    payload = load_json(args.input)
    resources = payload if isinstance(payload, list) else [payload]
    results = []

    for resource in resources:
        resource_type = resource.get("resource_type")
        assessment = assessments.get(resource_type)
        if not assessment:
            results.append({
                "resource_id": resource.get("resource_id"),
                "resource_type": resource_type,
                "error": "No assessment file for resource_type"
            })
            continue
        results.append(assess_resource(assessment, resource))

    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
