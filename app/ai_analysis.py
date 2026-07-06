"""AI enrichment for optimization engine findings — combines rule engine output with Azure OpenAI.

Improvements over original:
  - Parallel batch execution via ThreadPoolExecutor
  - Exponential-backoff retry on transient failures (tenacity)
  - Evidence-keyed response cache to avoid re-burning tokens on unchanged findings
  - Severity-based model routing (critical → gpt-4o, others → gpt-4o-mini when configured)
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import structlog
from sqlalchemy.orm import Session

from app.ai_client import build_ai_config, chat_completion
from app.services.system_settings import get_effective_config

log = structlog.get_logger(__name__)

_SYSTEM_PROMPT = """InfinityOps advisor. For each finding, write the user-facing recommendation and a one-line summary.
Use only supplied evidence — do not invent metrics or costs. Be concise.

Return JSON: {"enrichments":[{"index":0,"executive_summary":"...","recommendation":"...","implementation_steps":["..."],"risk_level":"low|medium|high","confidence_delta":0,"stale_likelihood":"low|medium|high|unknown","data_gaps":[]}]}
"""

_EVIDENCE_SCALAR_KEYS = (
    "avg_cpu_pct", "avg_memory_pct", "cpu_pct", "memory_pct", "memory_usage_pct",
    "disk_state", "age_days", "last_owner_name", "last_ownership_update", "time_created",
    "uptime_hours", "uptime_source", "is_stale", "monthly_cost_usd", "data_source",
    "determination", "summary", "vm_size", "suggested_sku", "tier", "sku",
    "http_listener_count", "throughput_bytes", "request_count", "power_state",
    "oldest_instance_time_created", "waste_score", "confidence_score",
)

# ---------------------------------------------------------------------------
# In-process enrichment cache  (keyed on evidence hash, TTL = process lifetime)
# ---------------------------------------------------------------------------
_enrich_cache: dict[str, dict[str, Any]] = {}
_enrich_cache_lock = threading.Lock()


def _evidence_cache_key(finding: dict[str, Any]) -> str:
    """Stable hash of rule_id + resource_id + evidence content — used to skip re-enrichment."""
    parts = (
        str(finding.get("rule_id") or ""),
        str(finding.get("resource_id") or finding.get("resource_name") or ""),
        json.dumps(finding.get("evidence") or {}, sort_keys=True, default=str),
    )
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def _cache_get(key: str) -> dict[str, Any] | None:
    with _enrich_cache_lock:
        return _enrich_cache.get(key)


def _cache_set(key: str, value: dict[str, Any]) -> None:
    with _enrich_cache_lock:
        _enrich_cache[key] = value


def clear_enrichment_cache() -> None:
    """Purge the in-process enrichment cache (e.g. after a full re-sync)."""
    with _enrich_cache_lock:
        _enrich_cache.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_ai_config(db: Session | None) -> dict[str, Any] | None:
    if db is None:
        return None
    try:
        raw = get_effective_config(db, "ai")
        return build_ai_config(raw)
    except Exception as exc:
        log.warning("ai.config_load_failed", error=str(exc))
        return None


def _select_findings(findings: list[dict[str, Any]], config: dict[str, Any]) -> list[tuple[int, dict[str, Any]]]:
    if config.get("ai_enrich_all_findings"):
        capped = findings[: config["ai_max_findings_per_run"]]
        return list(enumerate(capped))

    ranked = sorted(
        enumerate(findings),
        key=lambda item: float((item[1].get("estimated_savings_usd") or 0)),
        reverse=True,
    )
    return ranked[: config["ai_max_findings_per_run"]]


def _parse_evidence_dict(finding: dict[str, Any]) -> dict[str, Any]:
    evidence = finding.get("evidence") or {}
    if isinstance(evidence, str):
        try:
            evidence = json.loads(evidence)
        except Exception:
            evidence = {}
    return evidence if isinstance(evidence, dict) else {}


def _compact_metric_lines(evidence: dict[str, Any], *, limit: int = 8) -> list[str]:
    om = evidence.get("optimization_metrics") or {}
    if not isinstance(om, dict):
        return []
    lines: list[str] = []
    for block in (om.get("performance") or [], om.get("cost") or []):
        if not isinstance(block, list):
            continue
        for row in block:
            if not isinstance(row, dict) or len(lines) >= limit:
                break
            val = row.get("formatted") if row.get("formatted") not in (None, "") else row.get("value")
            if val in (None, ""):
                continue
            mid = row.get("id") or row.get("label") or "metric"
            status = row.get("status")
            lines.append(f"{mid}={val}" + (f"({status})" if status else ""))
    return lines


def _compact_check_lines(evidence: dict[str, Any], *, limit: int = 5) -> list[str]:
    checks = evidence.get("checks") or []
    if not isinstance(checks, list):
        return []
    lines: list[str] = []
    for check in checks[:limit]:
        if not isinstance(check, dict):
            continue
        signal = check.get("signal") or "signal"
        value = check.get("value")
        threshold = check.get("threshold")
        passed = check.get("passed")
        result = "ok" if passed else "fail"
        lines.append(f"{signal}: {value} vs {threshold} [{result}]")
    return lines


def _compact_finding(local_index: int, finding: dict[str, Any]) -> dict[str, Any]:
    """Token-efficient finding payload for batched AI requests."""
    evidence = _parse_evidence_dict(finding)
    signals = {
        k: evidence[k]
        for k in _EVIDENCE_SCALAR_KEYS
        if k in evidence and evidence[k] not in (None, "")
    }
    methodology = evidence.get("savings_methodology") or {}
    savings_usd = finding.get("estimated_savings_usd")
    if savings_usd in (None, "") and isinstance(methodology, dict):
        savings_usd = methodology.get("estimated_monthly_savings_usd")

    out: dict[str, Any] = {
        "index": local_index,
        "rule": finding.get("rule_id"),
        "resource": finding.get("resource_name"),
        "type": finding.get("resource_type"),
        "severity": finding.get("severity"),
        "savings_usd": savings_usd,
    }
    for k in ("determination", "summary"):
        if evidence.get(k):
            out[k] = evidence[k]
    if signals:
        out["signals"] = signals
    metric_lines = _compact_metric_lines(evidence)
    if metric_lines:
        out["metrics"] = metric_lines
    check_lines = _compact_check_lines(evidence)
    if check_lines:
        out["checks"] = check_lines
    if isinstance(methodology, dict) and methodology.get("formula"):
        out["savings_formula"] = methodology["formula"]
    return {k: v for k, v in out.items() if v not in (None, "", [], {})}


def _chunked(items: list[Any], size: int) -> list[list[Any]]:
    if size < 1:
        size = 1
    return [items[i:i + size] for i in range(0, len(items), size)]


def _max_tokens_for_batch(batch_len: int) -> int:
    return min(4000, max(600, 320 * batch_len + 120))


def _severity_model_override(batch: list[tuple[int, dict[str, Any]]], cfg: dict[str, Any]) -> dict[str, Any]:
    """Return a config copy with deployment overridden when ALL findings in a batch are critical.

    Allows routing critical findings to a higher-capability deployment (e.g. gpt-4o)
    while non-critical findings use a cost-efficient model (e.g. gpt-4o-mini).
    """
    critical_deployment = (cfg.get("openai_deployment_critical") or "").strip()
    if not critical_deployment:
        return cfg
    all_critical = all(
        str(finding.get("severity") or "").lower() == "critical"
        for _, finding in batch
    )
    if all_critical:
        return {**cfg, "openai_deployment": critical_deployment}
    return cfg


def _call_ai_batch_with_retry(
    cfg: dict[str, Any],
    batch: list[tuple[int, dict[str, Any]]],
    *,
    subscription_id: str | None = None,
    db: Session | None = None,
    max_retries: int = 3,
) -> dict[int, dict[str, Any]] | None:
    """Run one batched completion with exponential backoff retry."""
    import time as _time

    if not batch:
        return {}

    effective_cfg = _severity_model_override(batch, cfg)

    index_map: dict[int, int] = {}
    payload_findings: list[dict[str, Any]] = []
    for local_i, (global_idx, finding) in enumerate(batch):
        index_map[local_i] = global_idx
        payload_findings.append(_compact_finding(local_i, finding))

    payload: dict[str, Any] = {"findings": payload_findings}
    if subscription_id:
        payload["subscription_id"] = subscription_id

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": "Recommendations for this batch:\n"
            + json.dumps(payload, separators=(",", ":"), default=str),
        },
    ]

    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            content = chat_completion(
                effective_cfg,
                messages,
                max_tokens=_max_tokens_for_batch(len(batch)),
                db=db,
            )
            if content is None:
                # Transient failure — retry
                wait = 2 ** attempt
                log.warning("ai.batch_retry", attempt=attempt + 1, wait_sec=wait)
                _time.sleep(wait)
                continue

            parsed = _parse_json_response(content)
            if not parsed:
                return None

            out: dict[int, dict[str, Any]] = {}
            for row in parsed.get("enrichments") or []:
                try:
                    local_idx = int(row.get("index"))
                    global_idx = index_map.get(local_idx)
                except (TypeError, ValueError):
                    continue
                if global_idx is not None:
                    out[global_idx] = row
            return out
        except Exception as exc:
            last_exc = exc
            wait = 2 ** attempt
            log.warning("ai.batch_exception", attempt=attempt + 1, wait_sec=wait, error=str(exc))
            _time.sleep(wait)

    log.error("ai.batch_failed_all_retries", retries=max_retries, error=str(last_exc))
    return None


def _parse_json_response(content: str) -> dict[str, Any] | None:
    text = (content or "").strip()
    if not text:
        return None
    fence = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", text, re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _apply_enrichment(finding: dict[str, Any], enrichment: dict[str, Any]) -> dict[str, Any]:
    out = dict(finding)
    evidence = _parse_evidence_dict(out)

    rule_rec = (out.get("recommendation") or "").strip()
    rule_detail = (out.get("detail") or "").strip()
    if rule_rec or rule_detail:
        evidence["rule_engine"] = {
            k: v for k, v in {
                "recommendation": rule_rec or None,
                "detail": rule_detail or None,
            }.items() if v
        }

    ai_block: dict[str, Any] = {
        "executive_summary": enrichment.get("executive_summary"),
        "recommendation": enrichment.get("recommendation"),
        "implementation_steps": enrichment.get("implementation_steps") or [],
        "risk_level": enrichment.get("risk_level"),
        "stale_likelihood": enrichment.get("stale_likelihood"),
        "confidence_delta": enrichment.get("confidence_delta"),
        "data_gaps": enrichment.get("data_gaps") or [],
        "provider": "azure_openai",
    }
    evidence["ai_insight"] = {k: v for k, v in ai_block.items() if v not in (None, "", [])}
    out["evidence"] = evidence

    ai_rec = (enrichment.get("recommendation") or "").strip()
    ai_summary = (enrichment.get("executive_summary") or "").strip()
    if ai_rec:
        out["recommendation"] = ai_rec
        out["recommendation_source"] = "ai"
    if ai_summary:
        out["detail"] = ai_summary

    try:
        delta = int(enrichment.get("confidence_delta") or 0)
    except (TypeError, ValueError):
        delta = 0
    if delta:
        base = int(out.get("confidence_score") or 0)
        out["confidence_score"] = max(0, min(99, base + delta))

    risk = (enrichment.get("risk_level") or "").strip().lower()
    if risk in {"low", "medium", "high"}:
        out["ai_risk_level"] = risk

    return out


def enrich_analysis_with_ai(
    db: Session | None,
    result: dict[str, Any],
    *,
    config: dict[str, Any] | None = None,
    include_ai: bool | None = None,
) -> dict[str, Any]:
    """
    Replace user-facing recommendation text with Azure OpenAI output grounded in rule evidence.

    Runs whenever AI is configured unless include_ai=False.
    Batches execute in parallel via ThreadPoolExecutor.
    Results are cached by evidence hash to avoid re-burning tokens on unchanged findings.
    """
    if include_ai is False:
        return result

    findings = list(result.get("findings") or [])
    if not findings:
        return result

    cfg = config or _load_ai_config(db)
    if not cfg:
        result["ai_context"] = {"status": "not_configured", "message": "Configure Azure OpenAI in Settings."}
        return result

    selected = _select_findings(findings, cfg)
    if not selected:
        return result

    # ── Check in-process enrichment cache for each selected finding ──
    cache_keys = {global_idx: _evidence_cache_key(finding) for global_idx, finding in selected}
    uncached = [(global_idx, finding) for global_idx, finding in selected if not _cache_get(cache_keys[global_idx])]
    cached_count = len(selected) - len(uncached)

    batch_size = int(cfg.get("ai_batch_size") or 10)
    batches = _chunked(uncached, batch_size)
    subscription_id = result.get("subscription_id")

    by_index: dict[int, dict[str, Any]] = {}
    failed_batches = 0

    # ── Parallel batch execution ──
    max_workers = min(len(batches), 4) if batches else 1
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ai_batch") as pool:
        future_to_batch = {
            pool.submit(
                _call_ai_batch_with_retry,
                cfg,
                batch,
                subscription_id=subscription_id,
                db=db,
            ): batch
            for batch in batches
        }
        for future in as_completed(future_to_batch):
            batch_result = future.result()
            if batch_result is None:
                failed_batches += 1
            else:
                by_index.update(batch_result)

    # Store new results in cache
    for global_idx, enrichment in by_index.items():
        _cache_set(cache_keys[global_idx], enrichment)

    # Merge cached hits
    for global_idx, _ in selected:
        if global_idx not in by_index:
            cached = _cache_get(cache_keys[global_idx])
            if cached:
                by_index[global_idx] = cached

    if not by_index and failed_batches == len(batches):
        result["ai_context"] = {
            "status": "failed",
            "requested_count": len(selected),
            "batch_count": len(batches),
            "batch_size": batch_size,
        }
        return result

    updated = list(findings)
    enriched_count = 0
    for idx, finding in selected:
        enrichment = by_index.get(idx)
        if not enrichment:
            continue
        updated[idx] = _apply_enrichment(finding, enrichment)
        enriched_count += 1

    status = "completed"
    if failed_batches:
        status = "partial" if enriched_count else "failed"

    result["findings"] = updated
    result["ai_context"] = {
        "status": status,
        "enriched_count": enriched_count,
        "cached_count": cached_count,
        "requested_count": len(selected),
        "batch_count": len(batches),
        "batch_size": batch_size,
        "failed_batches": failed_batches,
        "deployment": cfg["openai_deployment"],
    }
    log.info(
        "ai.enrichment_completed",
        enriched=enriched_count,
        cached=cached_count,
        requested=len(selected),
        batches=len(batches),
        batch_size=batch_size,
        failed_batches=failed_batches,
    )
    return result
