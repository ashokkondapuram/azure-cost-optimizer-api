"""Assessment-driven optimization — catalog, runtime, normalization, signals."""

from app.assessment.catalog import (
    assessment_data_dir,
    get_assessment_for_arm_type,
    indexed_arm_types,
    load_assessment_index,
)
from app.assessment.runtime import (
    assess_data_quality,
    assess_resource,
    evaluate_assessment_rules,
    evaluate_condition,
    evaluate_condition_group,
    rule_to_finding,
)
from app.assessment.advisor_bridge import (
    JSON_EVALUATED_PILLARS,
    advisor_row_to_finding,
    build_policy_from_advisor,
    is_json_evaluated_rule,
)

__all__ = [
    "JSON_EVALUATED_PILLARS",
    "advisor_row_to_finding",
    "assessment_data_dir",
    "assess_data_quality",
    "assess_resource",
    "build_policy_from_advisor",
    "evaluate_assessment_rules",
    "evaluate_condition",
    "evaluate_condition_group",
    "get_assessment_for_arm_type",
    "indexed_arm_types",
    "is_json_evaluated_rule",
    "load_assessment_index",
    "rule_to_finding",
]
