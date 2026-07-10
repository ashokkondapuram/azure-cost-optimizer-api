"""Budgets optimization sub-engine."""
from __future__ import annotations

from typing import Any

from app.optimizer.platform.runtime.base import ResourceSubEngine
from app.optimizer.platform.cost.budget.analysis import analyze_budgets


class BudgetSubEngine(ResourceSubEngine):
    component = "Budgets"
    bucket_keys = ('budgets',)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        budgets = buckets.get("budgets") or []
        return analyze_budgets(self.engine, self.ctx.subscription_id, budgets, self.ctx.subscription_spend_usd)
