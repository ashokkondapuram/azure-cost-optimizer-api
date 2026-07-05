# Backend Fix: Populate Investigation Data for Actions

## Current Problem

When you click an action and see the drawer, the **Investigations section is empty**:
- ❌ AZURE ADVISOR - No data shown
- ❌ COST SIGNALS - Empty
- ❌ UTILIZATION METRICS - Empty  
- ❌ DECISION RULES APPLIED - Empty

This is because these JSON fields in the database are **empty objects `{}` or empty arrays `[]`**.

---

## Root Cause

When `OptimizationAction` is created in `app/optimizer/decision_engine.py:270`:

```python
action_row = OptimizationAction(
    id=str(uuid.uuid4()),
    subscription_id=sub,
    resource_id=rid,
    workflow_status="proposed",
    workflow_history_json="[]",
    **payload,  # ← Contains basic fields only
)
```

The `payload` includes:
- ✅ action_type (Resize, Shutdown, etc.)
- ✅ action_reason (text description)
- ✅ confidence (Medium, High, Low)
- ❌ advisor_finding (EMPTY - should be populated)
- ❌ cost_evidence (EMPTY - should be populated)
- ❌ utilization_evidence (EMPTY - should be populated)
- ❌ decision_rules_applied (EMPTY - should be populated)

---

## What Needs to Be Fixed

### 1. Populate `advisor_finding` from AdvisorRecommendation table

When action is created from Azure Advisor, fetch the related recommendation:

```python
# After creating action_row
if decision.get("advisor_recommendation_id"):
    advisor_rec = db.query(AdvisorRecommendation).filter(
        AdvisorRecommendation.recommendation_id == decision["advisor_recommendation_id"]
    ).first()
    
    if advisor_rec:
        action_row.advisor_finding = json.dumps({
            "impact": advisor_rec.impact,
            "recommendation": advisor_rec.recommendation,
            "savings": advisor_rec.potential_savings_usd,
        })
```

**Data source:** `AdvisorRecommendation` table
**Fields to include:**
- impact (High, Medium, Low)
- recommendation (text)
- savings (monthly amount)

---

### 2. Populate `cost_evidence` from findings data

Fetch findings that led to this action to get cost metrics:

```python
# Fetch findings for this resource
findings = db.query(OptimizationFinding).filter(
    OptimizationFinding.resource_id == rid,
    OptimizationFinding.subscription_id == sub,
).all()

cost_findings = [f for f in findings if f.category == "cost"]
if cost_findings:
    primary = cost_findings[0]
    action_row.cost_evidence = json.dumps({
        "metric": "Monthly compute cost",
        "current_cost": primary.current_monthly_cost,  # If available
        "estimated_savings": primary.estimated_savings_usd,
    })
```

**Data source:** `OptimizationFinding` or `CostData` table
**Fields to include:**
- metric (description of what's being measured)
- current_cost (current monthly cost)
- estimated_savings (potential savings)

---

### 3. Populate `utilization_evidence` from WorkloadProfile/metrics

Fetch resource utilization data to show why action is needed:

```python
# Fetch workload profile for resource
profile = db.query(WorkloadProfile).filter(
    WorkloadProfile.resource_id == rid,
).first()

if profile:
    action_row.utilization_evidence = json.dumps({
        "metric": f"{profile.metric_name} Utilization",  # CPU, Memory, etc.
        "average": round(profile.avg_utilization, 1),
        "peak": round(profile.peak_utilization, 1),
        "trend": profile.trend,  # Increasing, Stable, Decreasing
    })
```

**Data source:** `WorkloadProfile` or metrics tables
**Fields to include:**
- metric (CPU, Memory, Disk, Network, etc.)
- average (%)
- peak (%)
- trend (Stable, Increasing, Decreasing)

---

### 4. Populate `decision_rules_applied` from decision engine rules

Track which rules triggered this action:

```python
# When decision is made, capture which rules matched
rules_matched = []
if confidence_score > 80:
    rules_matched.append("High confidence decision engine match")
if avg_utilization < 30:
    rules_matched.append("Utilization below 30% average")
if peak_utilization < 50:
    rules_matched.append("Peak usage below 50%")
if estimated_savings > 1000:
    rules_matched.append("Cost savings > $1,000/month")

action_row.decision_rules_applied = json.dumps(rules_matched)
```

**Data source:** Decision engine logic
**What to capture:**
- Confidence rules (>80%, >60%, etc.)
- Utilization rules (avg/peak thresholds)
- Cost rules (savings thresholds)
- Trend rules (stable/increasing/decreasing)
- Risk rules (performance impact assessment)

---

## Implementation Plan

### Step 1: Add helper function to populate investigations
Create new function in `app/optimizer/decision_engine.py`:

```python
def populate_action_investigations(db: Session, action: OptimizationAction, decision: dict):
    """Fetch and populate investigation data from related tables."""
    
    # 1. Fetch advisor finding
    advisor_rec_id = decision.get("advisor_recommendation_id")
    if advisor_rec_id:
        advisor_rec = db.query(AdvisorRecommendation).filter_by(
            recommendation_id=advisor_rec_id
        ).first()
        if advisor_rec:
            action.advisor_finding = json.dumps({
                "impact": advisor_rec.impact,
                "recommendation": advisor_rec.recommendation,
                "savings": advisor_rec.potential_savings_usd or 0,
            })
    
    # 2. Fetch cost evidence from findings
    findings = db.query(OptimizationFinding).filter_by(
        resource_id=action.resource_id,
        subscription_id=action.subscription_id,
    ).all()
    
    cost_findings = [f for f in findings if f.category == "cost"]
    if cost_findings:
        f = cost_findings[0]
        action.cost_evidence = json.dumps({
            "metric": "Monthly compute cost",
            "current_cost": getattr(f, 'current_monthly_cost', None),
            "estimated_savings": f.estimated_savings_usd or 0,
        })
    
    # 3. Fetch utilization metrics from workload profile
    profile = db.query(WorkloadProfile).filter_by(
        resource_id=action.resource_id
    ).first()
    
    if profile:
        action.utilization_evidence = json.dumps({
            "metric": "CPU Utilization",  # or get from profile.metric_name
            "average": profile.utilization_variance_7d or 0,
            "peak": getattr(profile, 'peak_utilization', 0),
            "trend": profile.utilization_trend or "Unknown",
        })
    
    # 4. Set decision rules based on decision logic
    rules = []
    if decision.get("confidence", "").lower() in ["high", "very_high"]:
        rules.append("High confidence decision engine match")
    if decision.get("avg_utilization", 100) < 30:
        rules.append("Utilization below 30% average")
    if decision.get("peak_utilization", 100) < 50:
        rules.append("Peak usage below 50%")
    if decision.get("estimated_savings", 0) > 1000:
        rules.append("Cost savings > $1,000/month")
    if decision.get("performance_risk", "High") == "Low":
        rules.append("Low performance risk")
    
    action.decision_rules_applied = json.dumps(rules)
```

### Step 2: Call this function when creating actions
In `app/optimizer/decision_engine.py` around line 270:

```python
action_row = OptimizationAction(
    id=str(uuid.uuid4()),
    subscription_id=sub,
    resource_id=rid,
    workflow_status="proposed",
    workflow_history_json="[]",
    **payload,
)
db.add(action_row)

# NEW: Populate investigation data
populate_action_investigations(db, action_row, decision)

db.commit()
```

### Step 3: Test the fix
After implementation:
1. Run decision engine: POST `/optimize/actions/decide`
2. Query actions: GET `/optimize/actions/list`
3. Check response JSON - fields should be populated:
   ```json
   {
     "advisor_finding": {
       "impact": "High",
       "recommendation": "...",
       "savings": 1245
     },
     "cost_evidence": {
       "metric": "Monthly compute cost",
       "current_cost": 2100,
       "estimated_savings": 1245
     },
     "utilization_evidence": {
       "metric": "CPU Utilization",
       "average": 15,
       "peak": 40,
       "trend": "Stable"
     },
     "decision_rules_applied": [
       "High confidence decision engine match",
       "Utilization below 30% average",
       "Peak usage below 50%",
       "Cost savings > $1,000/month"
     ]
   }
   ```
4. Open drawer - all investigation sections populated ✅

---

## Data Source Summary

| Investigation | Source Table | Fields |
|---------------|--------------|--------|
| **Azure Advisor** | `AdvisorRecommendation` | impact, recommendation, savings |
| **Cost Evidence** | `OptimizationFinding` or `CostData` | metric, current_cost, savings |
| **Utilization** | `WorkloadProfile` or metrics | metric, avg%, peak%, trend |
| **Decision Rules** | Decision engine logic | matched rules + reasons |

---

## Frontend Dependency
The frontend drawer is ready to display this data. Once backend populates these fields, drawer will automatically show:
- ✅ AZURE ADVISOR findings
- ✅ COST SIGNALS with savings calculations
- ✅ UTILIZATION METRICS with trends
- ✅ DECISION RULES with checkmarks

---

## Timeline
- **Backend fix:** 2-4 hours (populate 4 JSON fields)
- **Testing:** 1 hour (run decision engine, verify data)
- **Frontend:** Already done (just needs data)

---

## Success Criteria
- [ ] advisor_finding populated with real Advisor data
- [ ] cost_evidence populated with cost metrics
- [ ] utilization_evidence populated with workload data
- [ ] decision_rules_applied populated with matched rules
- [ ] Drawer shows all investigation data
- [ ] Data persists in database

---

## Files to Modify
1. `app/optimizer/decision_engine.py` (add helper function + call it)
2. Possibly: `app/models.py` (ensure JSON fields exist)
3. Testing: Run decision engine and check response

---

**This fix bridges the gap between the comprehensive frontend UI and the backend data layer.** 🔗

