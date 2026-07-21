"""Assessment property definitions — source of truth for enrichment property keys."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from app.assessment.catalog import get_assessment_for_arm_type, load_assessment_index
from app.resources.registry import TECHNICAL_FETCH_SPECS

_ARM_TYPE_BY_CANONICAL: dict[str, str] = {
    ct: spec.arm_type
    for ct, spec in TECHNICAL_FETCH_SPECS.items()
    if getattr(spec, "arm_type", None)
}


def _arm_type_for_canonical(canonical_type: str) -> str:
    ct = (canonical_type or "").strip().lower()
    if ct in _ARM_TYPE_BY_CANONICAL:
        return _ARM_TYPE_BY_CANONICAL[ct]
    # Fallback: scan assessment index for matching assessment file slug
    slug = ct.split("/")[-1].replace("-", "")
    for item in load_assessment_index().get("items") or []:
        arm_type = str(item.get("resourceType") or "")
        assessment_file = str(item.get("assessmentFile") or "")
        if slug and slug in assessment_file.replace("-", "").lower():
            return arm_type
    return ""


@dataclass(frozen=True)
class AssessmentPropertyDef:
    property_key: str
    arm_path: str
    label: str
    value_type: str
    group_key: str
    unit: str = ""


def property_key_from_arm_path(arm_path: str) -> str:
    """Map assessment arm_path to a stable enrichment property key."""
    path = (arm_path or "").strip()
    if path == "sku.name":
        return "sku"
    if path.startswith("properties."):
        return path.split(".", 1)[1]
    return path.split(".")[-1]


def _v1_resource_properties(assessment: dict[str, Any]) -> list[AssessmentPropertyDef]:
    """Map legacy resourceProperties paths to enrichment property defs."""
    skip = frozenset({"id", "name", "type", "location", "tags"})
    out: list[AssessmentPropertyDef] = []
    for raw in assessment.get("resourceProperties") or []:
        text = str(raw).strip()
        if not text or text in skip:
            continue
        if text.startswith("properties."):
            arm_path = text
            leaf = text.split(".", 1)[1]
        else:
            arm_path = f"properties.{text}" if "." not in text else text
            leaf = text.split(".")[-1]
        label = leaf.replace("_", " ").replace("Bgp", "BGP")
        label = label[0].upper() + label[1:] if label else leaf
        out.append(
            AssessmentPropertyDef(
                property_key=property_key_from_arm_path(arm_path),
                arm_path=arm_path,
                label=label,
                value_type="string",
                group_key="configuration",
            )
        )
    return out


def _schema_v2_properties(assessment: dict[str, Any]) -> list[AssessmentPropertyDef]:
    schema = str(assessment.get("schema_version") or assessment.get("schemaVersion") or "")
    if not schema.startswith("2"):
        return _v1_resource_properties(assessment)
    azure_props = assessment.get("azure_properties") or {}
    out: list[AssessmentPropertyDef] = []
    for group in azure_props.get("groups") or []:
        group_key = str(group.get("group") or "configuration")
        for item in group.get("properties") or []:
            if not isinstance(item, dict):
                continue
            arm_path = str(item.get("arm_path") or "").strip()
            if not arm_path:
                continue
            out.append(
                AssessmentPropertyDef(
                    property_key=property_key_from_arm_path(arm_path),
                    arm_path=arm_path,
                    label=str(item.get("label") or property_key_from_arm_path(arm_path)),
                    value_type=str(item.get("type") or "string"),
                    group_key=group_key,
                    unit=str(item.get("unit") or ""),
                )
            )
    if out:
        return out
    return _v1_resource_properties(assessment)


@lru_cache(maxsize=64)
def property_defs_for_canonical(canonical_type: str) -> tuple[AssessmentPropertyDef, ...]:
    ct = (canonical_type or "").strip().lower()
    arm_type = _arm_type_for_canonical(ct)
    if not arm_type:
        return tuple()
    assessment = get_assessment_for_arm_type(arm_type)
    if not assessment:
        return tuple()
    return tuple(_schema_v2_properties(assessment))


def resolve_arm_path(row_dict: dict[str, Any], arm_path: str) -> Any:
    """Resolve assessment arm_path against a normalized resource row dict."""
    path = (arm_path or "").strip()
    if not path:
        return None

    if path == "sku.name":
        sku = row_dict.get("sku")
        if isinstance(sku, dict):
            return sku.get("name") or sku.get("tier")
        return sku

    if path == "location":
        return row_dict.get("location")

    if path == "zones":
        return row_dict.get("zones")

    if path.startswith("properties."):
        leaf = path.split(".", 1)[1]
        props = row_dict.get("properties") or {}
        if isinstance(props, dict) and leaf in props:
            return props.get(leaf)
        return None

    return row_dict.get(path)


def serialize_property_value(value: Any, value_type: str = "string") -> str | None:
    """Serialize a property value for individual column storage (not nested JSON blobs)."""
    if value is None or value == "":
        return None
    vtype = (value_type or "string").lower()
    if vtype == "boolean":
        return "Yes" if bool(value) else "No"
    if vtype == "number":
        try:
            num = float(value)
            return str(int(num)) if num.is_integer() else f"{num:g}"
        except (TypeError, ValueError):
            return str(value)
    if vtype == "datetime":
        return str(value)
    if vtype in {"array", "object"}:
        if isinstance(value, list):
            if not value:
                return None
            if all(not isinstance(v, (dict, list)) for v in value):
                return ", ".join(str(v) for v in value)
            return f"{len(value)} items"
        if isinstance(value, dict):
            if value.get("createOption"):
                return str(value.get("createOption"))
            if value.get("type"):
                return str(value.get("type"))
            keys = [k for k, v in value.items() if v not in (None, "", False)]
            if len(keys) == 1:
                return str(value.get(keys[0]))
            return f"{len(keys)} fields"
        return str(value)
    return str(value)
