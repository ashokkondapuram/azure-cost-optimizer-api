"""Ensure backend canonical resource types have frontend icon mappings."""

from app.resource_type_map import ARM_PROVIDER_TO_INTERNAL


def test_canonical_types_have_frontend_icon_map():
    """Every ARM-mapped internal type should exist in the frontend registry."""
    import json
    from pathlib import Path

    registry_path = (
        Path(__file__).resolve().parents[1]
        / "frontend"
        / "src"
        / "config"
        / "azureIconRegistry.js"
    )
    text = registry_path.read_text(encoding="utf-8")
    # Extract keys from CANONICAL_TYPE_KEYS block without importing JS
    start = text.index("export const CANONICAL_TYPE_KEYS = {")
    end = text.index("};", start)
    block = text[start:end]
    mapped = set()
    for line in block.splitlines():
        line = line.strip()
        if not line or line.startswith("//") or line.startswith("export"):
            continue
        if ":" in line:
            key = line.split(":", 1)[0].strip().strip("'\"")
            if key:
                mapped.add(key)

    internal_types = set(ARM_PROVIDER_TO_INTERNAL.values())
    missing = sorted(internal_types - mapped)
    assert not missing, f"Missing frontend icons for canonical types: {missing}"
