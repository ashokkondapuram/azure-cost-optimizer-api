# UI/UX feature improvements

**Status:** Superseded by [2026-07-ui-ux-advanced-improvements.md](../approved/2026-07-ui-ux-advanced-improvements.md) (approved Jul 3, 2026)  
**Author:** Engineering  
**Date:** Jun 30, 2026

## Implemented in this iteration

| # | Feature | Status |
|---|---------|--------|
| 2 | Bulk actions on findings | Done — list view checkboxes, `BulkActionBar`, `bulkUpdateFindingStatus` API |
| 7 | Finding status undo toast | Done — 5s delayed commit with Undo in `ToastContext` |
| 3 | Saved filter presets | Done — `useFilterPresets` + localStorage on Recommendations |
| 1 | Command palette (Cmd+K) | Done — `CommandPalette.jsx` in `App.js` |
| 8 | Custom column visibility | Done — `ColumnPicker` + `useColumnConfig` on `ResourceList` |
| 9 | PDF/print export | Done — `print.css` + `PrintExportButton` on Dashboard & Recommendations |
| 12 | Dashboard MTD vs last month KPI | Already shipped (`monthly_trend`) |

## Not yet implemented

| # | Feature | Notes |
|---|---------|-------|
| 4 | Interactive charts (zoom/toggle) | Recharts brush + series toggles |
| 5 | Real-time SSE job progress | Backend `GET /events/jobs/{sub}` + `EventSource` |
| 6 | Cost period comparison | Side-by-side periods in Cost Explorer |
| 10 | Activity log / audit trail | `FindingActivity` table + API |
| 11 | Inline resource tagging | ARM proxy `PATCH /resources/{id}/tags` |
| 13 | Mobile card view | Responsive table → cards below 768px |

## Verification checklist

- [x] Bulk: select findings → Mark resolved/dismissed → bulk API updates
- [x] Undo: resolve finding → Undo within 5s → status unchanged
- [x] Presets: save filter → chip restores filters after refresh
- [x] Cmd+K: search page/resource → Enter navigates
- [x] Columns: hide column → persists in localStorage
- [x] Print: Export PDF opens print dialog without sidebar
- [ ] SSE: EventStream tab shows job events (not built)
- [ ] Cost compare: dashed prior-month line (not built)
