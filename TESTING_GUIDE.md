# Testing Guide - Phase 1 & 2 UI/UX Improvements

## Quick Start

### 1. Start the Dev Server
```bash
cd frontend
npm install  # If needed
npm start
```

The app will open at `http://localhost:3000`

### 2. Navigate to OptimizationHub
- URL: `http://localhost:3000/optimization`
- Or use sidebar: Click "Optimization" → "Overview"

---

## What's New to Test

### Phase 1: Progressive Loading & Timeouts
**Location:** OptimizationHub Overview Tab

What to look for:
1. **Page loads fast (<2s)**
   - KPI cards (4 cards at top) appear instantly
   - ActionLifecycle section loads below with skeleton animation
   - No page freeze

2. **Skeleton loaders work**
   - When ActionLifecycle is loading, see pulsing skeleton
   - Smooth animation (not jerky)

3. **Timeout handling (3s max)**
   - If API slow, section still renders (doesn't error)
   - Data comes from cache or empty defaults

---

### Phase 2: Filtering & Organization
**Location:** OptimizationActions Tab

What to test:

#### 1. Filter Bar
- Below KPI cards, you'll see 3 dropdowns:
  - **Status**: Try filtering by "proposed", "approved", etc.
  - **Action type**: Filter by Resize, Shutdown, etc.
  - **Resource type**: Filter by VM, AKS, etc.
- Table updates immediately
- Combine multiple filters (Status = "proposed" AND Type = "Resize")

#### 2. Resource Group Column
- Table should show: Resource | **Resource group** | Action | Confidence | Savings | Status | Risk
- Resource group should display correctly (e.g., "rg-eastus")
- Works in both regular table and virtual-scrolled view

#### 3. Grouping Toggle
- Below filter bar, see "Group by" toggle buttons
- Try: "Flat" (all in table) → "Resource Type" (grouped) → "Resource Group" (grouped)
- Each group shows count of actions + total savings

---

### Phase 2: Modal Redesign
**How to access:** OptimizationActions Tab → Click any row

What to look for:
1. **Modal structure is clearer**
   - Header with resource name
   - 4 sections: Details | Recommendation | Approval | Audit Trail

2. **Details section**
   - Type, Confidence, Current Status shown as chips
   - Estimated savings highlighted in blue

3. **Recommendation section**
   - Shows the action reasoning

4. **Approval section (admin only)**
   - Dropdown to change status
   - Options: Approved, Executed, Rejected, Deferred, Proposed

5. **Audit trail**
   - Notes textarea
   - Save button updates action

---

## Testing Checklist

Use `TEST_CHECKLIST.md` for detailed testing steps.

### Quick Smoke Test (5 min)
```
1. Load OptimizationHub → See KPI cards fast ✓
2. Go to Actions → See filters work ✓
3. See Resource Group column ✓
4. Click action → Modal displays cleanly ✓
5. No console errors ✓
```

### Full Test (30 min)
Follow complete checklist in `TEST_CHECKLIST.md`

---

## Common Issues & Troubleshooting

### Issue: Filters don't work
**Solution:** 
- Refresh page (Cmd+R / Ctrl+R)
- Check browser console (F12 → Console tab)
- Verify data exists (KPI cards should show counts)

### Issue: Skeleton doesn't animate
**Solution:**
- Check CSS loaded (DevTools → Styles → search "skeleton")
- Try slower network (DevTools → Network → Slow 3G)
- Restart dev server

### Issue: Modal doesn't open
**Solution:**
- Click directly on table row (not checkbox)
- Check console for errors
- Try different row (first action)

### Issue: Resource group shows blank
**Solution:**
- API might not be returning data
- Check Network tab → find `optimization-actions` request → see response
- Verify resource_group field exists in JSON

---

## Performance Targets

| Metric | Target | How to measure |
|--------|--------|-----------------|
| Initial load | <2s | DevTools → Network → measure load time |
| Filter update | <500ms | Change filter, count time to table update |
| Modal open | <300ms | Click row, count time to modal appear |
| Skeleton animation | 60fps | DevTools → Rendering → FPS meter |
| No jank | Smooth | Scroll table, should be fluid |

---

## API Endpoints Involved

| Endpoint | Purpose | Timeout | Tab |
|----------|---------|---------|-----|
| `/optimize/findings-summary` | Summary count | 3s | Overview, Recommendations |
| `/optimize/trends` | Action lifecycle data | 3s | Overview, Actions |
| `/optimize/actions` | List of actions | None | Actions |
| `/optimize/resources/analysis` | Resource metrics | None | Drawer |

---

## File Changes Summary

**New files:**
- `frontend/src/components/visual/LazySection.jsx`
- `frontend/src/components/visual/SectionSkeleton.jsx`
- `frontend/src/hooks/useQueryWithTimeout.js`
- `frontend/src/components/filtering/GroupBySelect.jsx`
- `frontend/src/components/optimization/ActionsFilterBar.jsx`

**Modified files:**
- `frontend/src/pages/OptimizationActions.jsx` (filters, resource group column)
- `frontend/src/pages/Recommendations.jsx` (timeout handling)
- `frontend/src/components/optimization/OptimizationHubOverview.jsx` (lazy loading)
- `frontend/src/components/optimization/ActionApprovalModal.jsx` (redesign)
- `frontend/src/index.css` (styling)

---

## Next Steps After Testing

1. **If all tests pass:**
   - Create PR for code review
   - Merge to main branch
   - Deploy to staging

2. **If issues found:**
   - Document in TEST_CHECKLIST.md
   - Create GitHub issues
   - Fix and re-test

3. **Future improvements:**
   - Apply similar patterns to other tabs
   - Optimize database queries
   - Add more advanced filtering

---

**Happy testing!** 🚀

Questions? Check browser console (F12) for error details.

