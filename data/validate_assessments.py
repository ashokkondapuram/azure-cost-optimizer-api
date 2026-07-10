#!/usr/bin/env python3
import json
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parent
ASSESSMENT_GLOB = "*-assessment.json"
REQUIRED_KEYS = {
    "schemaVersion",
    "resourceType",
    "assessmentName",
    "versionDate",
    "strategy",
    "apis",
    "lowCallCollectionPlan",
    "pythonAssessment",
    "runtimeContract",
    "analyzerContract",
    "costManagementCharging",
    "assessmentContract",
    "assessmentRules",
    "metricAssessmentRules",
    "propertyAssessmentRules",
    "bestOptimizationRules",
    "actionOutcomeRules",
    "recommendationRules",
    "pricingFilters",
    "knownLimitations",
    "documentationSources"
}

ALLOWED_RECOMMENDATION_ACTIONS = {
    "upgrade",
    "downgrade",
    "stay",
    "stop_or_delete",
    "investigate",
}


def load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_structure(path, data):
    errors = []
    missing = sorted(REQUIRED_KEYS - set(data))
    if missing:
        errors.append(f"{path.name}: missing required keys: {', '.join(missing)}")

    rules = data.get("recommendationRules", [])
    if not isinstance(rules, list) or not rules:
        errors.append(f"{path.name}: recommendationRules must be a non-empty list")
    else:
        for index, rule in enumerate(rules):
            for key in ("id", "pillar", "severity", "condition", "recommendation"):
                if key not in rule:
                    errors.append(f"{path.name}: recommendationRules[{index}] missing {key}")
            condition = rule.get("condition")
            if isinstance(condition, str):
                errors.append(f"{path.name}: recommendationRules[{index}].condition must be structured, not prose")
            elif not isinstance(condition, dict):
                errors.append(f"{path.name}: recommendationRules[{index}].condition must be an object")
            else:
                expected_condition_flags = {
                    "evaluator": "field_operator_value",
                    "pythonCompatible": True,
                    "aiCompatible": True
                }
                for key, expected in expected_condition_flags.items():
                    if condition.get(key) != expected:
                        errors.append(f"{path.name}: recommendationRules[{index}].condition.{key} must be {expected!r}")
                if not isinstance(condition.get("pythonExpression"), str) or not condition.get("pythonExpression"):
                    errors.append(f"{path.name}: recommendationRules[{index}].condition.pythonExpression must be a non-empty string")
                if not isinstance(condition.get("requiredSignalPaths"), list) or not condition.get("requiredSignalPaths"):
                    errors.append(f"{path.name}: recommendationRules[{index}].condition.requiredSignalPaths must be a non-empty list")
                if condition.get("type") not in {"all", "any"}:
                    errors.append(f"{path.name}: recommendationRules[{index}].condition.type must be all or any")
                conditions = condition.get("conditions")
                if not isinstance(conditions, list) or not conditions:
                    errors.append(f"{path.name}: recommendationRules[{index}].condition.conditions must be a non-empty list")
                else:
                    for cond_index, cond in enumerate(conditions):
                        for key in ("field", "operator", "value"):
                            if key not in cond:
                                errors.append(f"{path.name}: recommendationRules[{index}].condition.conditions[{cond_index}] missing {key}")
            if rule.get("manualAssessmentAllowed") is not False:
                errors.append(f"{path.name}: recommendationRules[{index}].manualAssessmentAllowed must be false")
            if rule.get("aiAssessmentAllowed") is not False:
                errors.append(f"{path.name}: recommendationRules[{index}].aiAssessmentAllowed must be false")
            if rule.get("pythonCompatible") is not True:
                errors.append(f"{path.name}: recommendationRules[{index}].pythonCompatible must be true")
            if rule.get("aiCompatible") is not True:
                errors.append(f"{path.name}: recommendationRules[{index}].aiCompatible must be true")
            action = rule.get("recommendationAction") or rule.get("actionOutcome")
            if action is not None and action not in ALLOWED_RECOMMENDATION_ACTIONS:
                errors.append(f"{path.name}: recommendationRules[{index}] has invalid recommendationAction {action!r}")

    low_call = data.get("lowCallCollectionPlan", {})
    if not isinstance(low_call, dict):
        errors.append(f"{path.name}: lowCallCollectionPlan must be an object")
    else:
        for key in ("goal", "callReductionPrinciples", "minimumCallFlowPerSubscription", "callBudgetModes"):
            if key not in low_call:
                errors.append(f"{path.name}: lowCallCollectionPlan missing {key}")

    python_assessment = data.get("pythonAssessment", {})
    if not isinstance(python_assessment, dict):
        errors.append(f"{path.name}: pythonAssessment must be an object")
    else:
        expected_flags = {
            "manualAssessmentAllowed": False,
            "aiAssessmentAllowed": False,
            "runtimeMayUseNaturalLanguageConditions": False
        }
        for key, expected in expected_flags.items():
            if python_assessment.get(key) != expected:
                errors.append(f"{path.name}: pythonAssessment.{key} must be {expected!r}")
        if python_assessment.get("dataSource") != "database":
            errors.append(f"{path.name}: pythonAssessment.dataSource must be 'database'")
        if python_assessment.get("azureApiCallsAllowed") is not False:
            errors.append(f"{path.name}: pythonAssessment.azureApiCallsAllowed must be false")
        deterministic_cases = python_assessment.get("deterministicCases")
        if not isinstance(deterministic_cases, dict) or not deterministic_cases:
            errors.append(f"{path.name}: pythonAssessment.deterministicCases must be a non-empty object")
        else:
            for level, conditions in deterministic_cases.items():
                if not isinstance(conditions, list):
                    errors.append(f"{path.name}: deterministicCases.{level} must be a list")
                    continue
                for index, condition in enumerate(conditions):
                    for key in ("field", "operator", "value"):
                        if key not in condition:
                            errors.append(f"{path.name}: deterministicCases.{level}[{index}] missing {key}")

    runtime_contract = data.get("runtimeContract", {})
    if not isinstance(runtime_contract, dict):
        errors.append(f"{path.name}: runtimeContract must be an object")
    else:
        expected_contract = {
            "assessmentMode": "db_backed_deterministic_rule_evaluation",
            "manualAssessmentAllowed": False,
            "aiAssessmentAllowed": False,
            "naturalLanguageConditionsAllowed": False,
            "recommendationRulesUseStructuredConditions": True
        }
        for key, expected in expected_contract.items():
            if runtime_contract.get(key) != expected:
                errors.append(f"{path.name}: runtimeContract.{key} must be {expected!r}")
        if runtime_contract.get("runtimeInput") != "normalized_resource_record_from_database":
            errors.append(f"{path.name}: runtimeContract.runtimeInput must be normalized_resource_record_from_database")
        if runtime_contract.get("azureApiCallsAllowed") is not False:
            errors.append(f"{path.name}: runtimeContract.azureApiCallsAllowed must be false")
        if runtime_contract.get("costManagementCallsAllowed") is not False:
            errors.append(f"{path.name}: runtimeContract.costManagementCallsAllowed must be false")

    analyzer_contract = data.get("analyzerContract", {})
    if not isinstance(analyzer_contract, dict):
        errors.append(f"{path.name}: analyzerContract must be an object")
    else:
        expected_analyzer = {
            "dataSource": "database_normalized_azure_resource_record",
            "rulesSource": "this_assessment_json_file",
            "azureApiCallsAtRecommendationTimeAllowed": False,
            "manualAssessmentAllowed": False,
            "aiAssessmentRequired": False,
            "naturalLanguageAssessmentAllowed": False,
            "deterministicEvaluationRequired": True,
        }
        for key, expected in expected_analyzer.items():
            if analyzer_contract.get(key) != expected:
                errors.append(f"{path.name}: analyzerContract.{key} must be {expected!r}")
        if set(analyzer_contract.get("actionPriority", [])) != ALLOWED_RECOMMENDATION_ACTIONS:
            errors.append(f"{path.name}: analyzerContract.actionPriority must contain all allowed recommendation actions")

    charging = data.get("costManagementCharging", {})
    if not isinstance(charging, dict):
        errors.append(f"{path.name}: costManagementCharging must be an object")
    else:
        for key in ("billingResourceIdStrategy", "serviceNames", "primaryChargeDrivers", "expectedMeters", "costOptimizationSignals", "costManagementQuery"):
            if key not in charging:
                errors.append(f"{path.name}: costManagementCharging missing {key}")

    assessment_contract = data.get("assessmentContract", {})
    if not isinstance(assessment_contract, dict):
        errors.append(f"{path.name}: assessmentContract must be an object")
    elif assessment_contract.get("rulesAreDeterministic") is not True:
        errors.append(f"{path.name}: assessmentContract.rulesAreDeterministic must be true")
    else:
        actions = assessment_contract.get("allowedRecommendationActions")
        if set(actions or []) != ALLOWED_RECOMMENDATION_ACTIONS:
            errors.append(f"{path.name}: assessmentContract.allowedRecommendationActions must include upgrade, downgrade, stay, stop_or_delete, investigate")
        if assessment_contract.get("everyRuleIncludesRecommendationAction") is not True:
            errors.append(f"{path.name}: assessmentContract.everyRuleIncludesRecommendationAction must be true")
        if assessment_contract.get("analyzerMustNotCallAzureApis") is not True:
            errors.append(f"{path.name}: assessmentContract.analyzerMustNotCallAzureApis must be true")
        if assessment_contract.get("analyzerMustUseDbSnapshot") is not True:
            errors.append(f"{path.name}: assessmentContract.analyzerMustUseDbSnapshot must be true")

    assessment_rules = data.get("assessmentRules", [])
    if not isinstance(assessment_rules, list) or not assessment_rules:
        errors.append(f"{path.name}: assessmentRules must be a non-empty list")
    else:
        for index, rule in enumerate(assessment_rules):
            for key in ("id", "pillar", "severity", "condition", "output", "requiredData"):
                if key not in rule:
                    errors.append(f"{path.name}: assessmentRules[{index}] missing {key}")
            cond = rule.get("condition", {})
            if not isinstance(cond, dict) or cond.get("type") not in {"all", "any"}:
                errors.append(f"{path.name}: assessmentRules[{index}].condition must be grouped all/any object")
            elif not isinstance(cond.get("conditions"), list) or not cond.get("conditions"):
                errors.append(f"{path.name}: assessmentRules[{index}].condition.conditions must be non-empty")
            else:
                for cond_index, item in enumerate(cond["conditions"]):
                    for key in ("path", "operator"):
                        if key not in item:
                            errors.append(f"{path.name}: assessmentRules[{index}].condition.conditions[{cond_index}] missing {key}")
            output = rule.get("output", {})
            if not isinstance(output, dict) or not output.get("message"):
                errors.append(f"{path.name}: assessmentRules[{index}].output.message is required")
            action = rule.get("recommendationAction") or rule.get("actionOutcome")
            if action not in ALLOWED_RECOMMENDATION_ACTIONS:
                errors.append(f"{path.name}: assessmentRules[{index}] must include a valid recommendationAction/actionOutcome")
            elif isinstance(output, dict) and output.get("recommendationAction") not in ALLOWED_RECOMMENDATION_ACTIONS:
                errors.append(f"{path.name}: assessmentRules[{index}].output.recommendationAction must be valid")
            if output.get("action") not in ALLOWED_RECOMMENDATION_ACTIONS:
                errors.append(f"{path.name}: assessmentRules[{index}].output.action must be a normalized recommendation action")

    for section_name in ("metricAssessmentRules", "propertyAssessmentRules", "actionOutcomeRules"):
        focused_rules = data.get(section_name, [])
        if not isinstance(focused_rules, list):
            errors.append(f"{path.name}: {section_name} must be a list")
        elif not focused_rules:
            errors.append(f"{path.name}: {section_name} must not be empty")
        else:
            for index, rule in enumerate(focused_rules):
                for key in ("id", "pillar", "severity", "condition", "output", "requiredData"):
                    if key not in rule:
                        errors.append(f"{path.name}: {section_name}[{index}] missing {key}")
                output = rule.get("output", {})
                if not isinstance(output, dict) or not output.get("message"):
                    errors.append(f"{path.name}: {section_name}[{index}].output.message is required")
                action = rule.get("recommendationAction") or rule.get("actionOutcome")
                if action not in ALLOWED_RECOMMENDATION_ACTIONS:
                    errors.append(f"{path.name}: {section_name}[{index}] must include a valid recommendationAction/actionOutcome")
                elif output.get("recommendationAction") not in ALLOWED_RECOMMENDATION_ACTIONS:
                    errors.append(f"{path.name}: {section_name}[{index}].output.recommendationAction must be valid")
                if output.get("action") not in ALLOWED_RECOMMENDATION_ACTIONS:
                    errors.append(f"{path.name}: {section_name}[{index}].output.action must be a normalized recommendation action")

    best_rules = data.get("bestOptimizationRules", [])
    if not isinstance(best_rules, list):
        errors.append(f"{path.name}: bestOptimizationRules must be a list")
    elif len(best_rules) < 10:
        errors.append(f"{path.name}: bestOptimizationRules must contain at least 10 rules")
    else:
        for index, rule in enumerate(best_rules):
            for key in ("id", "pillar", "severity", "condition", "output", "requiredData"):
                if key not in rule:
                    errors.append(f"{path.name}: bestOptimizationRules[{index}] missing {key}")
            output = rule.get("output", {})
            if not isinstance(output, dict) or not output.get("message"):
                errors.append(f"{path.name}: bestOptimizationRules[{index}].output.message is required")
            action = rule.get("recommendationAction") or rule.get("actionOutcome")
            if action not in ALLOWED_RECOMMENDATION_ACTIONS:
                errors.append(f"{path.name}: bestOptimizationRules[{index}] must include a valid recommendationAction/actionOutcome")
            elif output.get("recommendationAction") not in ALLOWED_RECOMMENDATION_ACTIONS:
                errors.append(f"{path.name}: bestOptimizationRules[{index}].output.recommendationAction must be valid")
            if output.get("action") not in ALLOWED_RECOMMENDATION_ACTIONS:
                errors.append(f"{path.name}: bestOptimizationRules[{index}].output.action must be a normalized recommendation action")

    return errors


def validate_with_jsonschema(schema_path, assessment_paths):
    try:
        import jsonschema
    except Exception:
        return ["jsonschema package not installed; skipped JSON Schema validation"]

    schema = load_json(schema_path)
    errors = []
    for path in assessment_paths:
        try:
            jsonschema.validate(load_json(path), schema)
        except jsonschema.ValidationError as exc:
            errors.append(f"{path.name}: schema validation failed: {exc.message}")
    return errors


def classify_score(score, matrix):
    for level in matrix["classificationLevels"]:
        low, high = level["scoreRange"]
        if low <= score <= high:
            return level["level"]
    return "unknown"


def deterministic_classify(resource_type, signals, matrix):
    score = matrix["defaultScoring"]["startScore"]
    caps = []
    thresholds = matrix["resourceCaseThresholds"].get(resource_type, {})

    worst = thresholds.get("worst", {})
    warning = thresholds.get("warning", {})

    for key, expected in worst.items():
        if key.endswith("Min"):
            base = key[:-3]
            if signals.get(base, 0) >= expected:
                score -= matrix["defaultScoring"]["deductions"]["critical"]
        elif key.endswith("Max"):
            base = key[:-3]
            value = signals.get(base)
            if value is not None and value <= expected:
                score -= matrix["defaultScoring"]["deductions"]["critical"]
        elif signals.get(key) == expected:
            score -= matrix["defaultScoring"]["deductions"]["critical"]

    for key, expected in warning.items():
        if key.endswith("Min"):
            base = key[:-3]
            if signals.get(base, 0) >= expected:
                score -= matrix["defaultScoring"]["deductions"]["medium"]
        elif key.endswith("Max"):
            base = key[:-3]
            value = signals.get(base)
            if value is not None and value <= expected:
                score -= matrix["defaultScoring"]["deductions"]["medium"]
        elif signals.get(key) == expected:
            score -= matrix["defaultScoring"]["deductions"]["medium"]

    if signals.get("anyCriticalSecurityFinding"):
        caps.append(matrix["defaultScoring"]["caps"]["anyCriticalSecurityFinding"])
    if signals.get("anyHighSecurityFinding"):
        caps.append(matrix["defaultScoring"]["caps"]["anyHighSecurityFinding"])
    if signals.get("missingRequiredMetrics"):
        caps.append(matrix["defaultScoring"]["caps"]["missingRequiredMetrics"])
    if signals.get("missingCostData"):
        caps.append(matrix["defaultScoring"]["caps"]["missingCostData"])

    score = max(0, min(100, score))
    if caps:
        score = min(score, min(caps))
    return {
        "resource_type": resource_type,
        "score": score,
        "classification": classify_score(score, matrix)
    }


def main():
    assessment_paths = sorted(ROOT.glob(ASSESSMENT_GLOB))
    assessment_paths = [
        path for path in assessment_paths
        if path.name not in {"assessment-case-matrix.json"}
    ]
    schema_path = ROOT / "assessment-file.schema.json"
    matrix_path = ROOT / "assessment-case-matrix.json"

    all_errors = []
    for path in assessment_paths:
        try:
            data = load_json(path)
        except Exception as exc:
            all_errors.append(f"{path.name}: invalid JSON: {exc}")
            continue
        all_errors.extend(validate_structure(path, data))

    if schema_path.exists():
        schema_errors = validate_with_jsonschema(schema_path, assessment_paths)
        all_errors.extend(error for error in schema_errors if not error.startswith("jsonschema package"))
        skipped_schema = [error for error in schema_errors if error.startswith("jsonschema package")]
    else:
        skipped_schema = ["assessment-file.schema.json missing; skipped JSON Schema validation"]

    if matrix_path.exists():
        matrix = load_json(matrix_path)
        covered = set(matrix.get("resourceCaseThresholds", {}))
        for path in assessment_paths:
            resource_type = load_json(path).get("resourceType")
            if resource_type not in covered:
                all_errors.append(f"{path.name}: resourceType {resource_type} missing from assessment-case-matrix.json")
    else:
        all_errors.append("assessment-case-matrix.json missing")

    if all_errors:
        print("FAILED")
        for error in all_errors:
            print(f"- {error}")
        return 1

    print("PASSED")
    print(f"assessment_files={len(assessment_paths)}")
    for path in assessment_paths:
        data = load_json(path)
        print(f"- {path.name}: {data['resourceType']}")
    for note in skipped_schema:
        print(f"note: {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
