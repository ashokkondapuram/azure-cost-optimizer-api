# UI/UX Testing Checklist - Phase 1 & 2

## Setup
```bash
cd frontend
npm start
```
Navigate to: http://localhost:3000/optimization

---

## 1. OptimizationHub Overview Tab ✓

### Progressive Loading
- [ ] KPI cards (4 cards) load immediately
- [ ] ActionLifecycle section shows skeleton loader initially
- [ ] ActionLifecycle loads when scrolling down
- [ ] No blocking on slow API calls

### Timeout Handling
- [ ] If trends API times out (>3s), ActionLifecycle still renders with empty data
- [ ] Page doesn't hang or error out

### Visual
- [ ] Skeleton animations pulse smoothly
- [ ] Transitions feel responsive
- [ ] Layout doesn't shift when data loads

---

## 2. OptimizationActions Tab ✓

### Filter Bar
- [ ] Filter bar displays below KPI cards
- [ ] Status, Action Type, Resource Type filters work
- [ ] Filters update table immediately
- [ ] Multiple filters can be combined

### Resource Group Column
- [ ] New "Resource group" column visible
- [ ] Column positioned after resource name
- [ ] Resource group names display correctly
- [ ] Shows '—' for missing values
- [ ] Works in both table and virtualized (scrolled) view

### Grouping Toggle
- [ ] "Resource type" grouping shows action counts per type
- [ ] "Resource group" grouping shows action counts per group
- [ ] Flat view shows all actions in table
- [ ] Switching between groupings works smoothly

### Table Performance
- [ ] Table scrolls smoothly with 50+ actions
- [ ] Virtual scrolling activates for 80+ items
- [ ] No lag when toggling checkboxes

### Timeout Handling
- [ ] If trends API times out, ActionLifecycle (lifecycle stepper) still renders

---

## 3. ActionApprovalModal (Review Action Dialog) ✓

### Open Modal
- [ ] Click any action row to open modal
- [ ] Modal displays resource name in header
- [ ] Modal shows close button (×)

### Content Sections
- [ ] **Action details section:**
  - [ ] Type shows action chip (Resize, Shutdown, etc.)
  - [ ] Confidence score displays
  - [ ] Current status shows (Proposed, Approved, etc.)
  - [ ] Est. savings/mo highlighted in blue (if >0)

- [ ] **Recommendation section:**
  - [ ] Action reason/recommendation visible
  - [ ] Clear, readable text

- [ ] **Approval section (admin only):**
  - [ ] Status dropdown visible
  - [ ] Can select different statuses
  - [ ] Options: Approved, Executed, Rejected, Deferred, Proposed

- [ ] **Audit trail section:**
  - [ ] Textarea for notes
  - [ ] Placeholder text visible
  - [ ] Can type without issues

### Buttons
- [ ] Cancel button closes modal
- [ ] Save button updates action (admin only)
- [ ] Disabled state shows when saving

### Mobile Responsive
- [ ] On small screens, grid stacks to single column
- [ ] Modal content fits without horizontal scroll
- [ ] All buttons accessible

---

## 4. Recommendations Tab ✓

### Page Load
- [ ] Summary section shows findings count
- [ ] Filters visible
- [ ] Table/list displays findings

### Timeout Handling
- [ ] If findings-summary API times out, page still renders
- [ ] Summary shows 0 values instead of error

### Filters
- [ ] Filter controls visible
- [ ] Filters apply to findings list
- [ ] Multiple filters work together

---

## 5. Console & Errors ✓

### DevTools Console
- [ ] No JavaScript errors
- [ ] No warnings about missing props
- [ ] No warnings about unused variables
- [ ] Network tab shows API calls with 3s timeout pattern

### Network Activity
- [ ] API calls succeed (<3s)
- [ ] If timeout, no error state (graceful fallback)
- [ ] No excessive/duplicate requests

---

## 6. Browser Compatibility ✓

### Desktop (Chrome, Firefox, Safari, Edge)
- [ ] Layouts render correctly
- [ ] Filters work
- [ ] Modals display properly
- [ ] Animations smooth

### Mobile / Tablet
- [ ] Responsive layout adapts
- [ ] Filter bar stacks on narrow screens
- [ ] Modal fits viewport
- [ ] Touch interactions work (buttons, selects)

### Performance
- [ ] Page loads in <2s
- [ ] No jank/stutter when scrolling
- [ ] Animations run at 60fps

---

## 7. Data Validation ✓

### Filters
- [ ] Resource group filter shows correct groups
- [ ] Action type filter shows available types
- [ ] Status filter shows available statuses

### Modal Data
- [ ] Resource name matches clicked row
- [ ] Action type matches row data
- [ ] Confidence score matches
- [ ] Savings amount accurate

### Grouping
- [ ] Group counts accurate
- [ ] Total savings per group calculated correctly
- [ ] Nested resource rows under group headers

---

## Issues Found

| Issue | Severity | Component | Status |
|-------|----------|-----------|--------|
| (none yet) | - | - | - |

---

## Sign Off

- [ ] All critical tests passed
- [ ] No blocking issues found
- [ ] Ready for production deployment

**Tested by:** ________________  
**Date:** ________________  
**Notes:** ________________

