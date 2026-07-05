# UI/UX advanced improvements

**Status:** Approved  
**Author:** Engineering  
**Date:** Jul 3, 2026  
**Approved:** Jul 3, 2026  
**Extends:** [2026-06-ui-ux-improvements.md](../drafts/2026-06-ui-ux-improvements.md) (partial items shipped; remainder folded into this spec)

## Alignment with current codebase

| Plan item | Already in repo | Notes |
|-----------|-----------------|-------|
| 1A Responsive | Partial | Sidebar collapse exists; mobile card view still open (see Jun spec #13) |
| 1B Optimization hub | Partial | `OptimizationHubLinks.jsx` links Actions / Scoreboard / Monitor — not a unified tabbed page |
| 1C Drawer reorder | — | `ResourceInsightDrawer.jsx`; `usePersistedState` exists |
| 2A Advanced filters | Partial | `useFilterPresets` on Recommendations; `FilterBar` everywhere; sort params not universal |
| 2B SSE | — | Listed as not built in Jun spec #5 |
| 2C Bulk ops | Partial | `BulkActionBar` + findings bulk API; not on Actions/Resources tagging |
| 2D Inline metrics | Partial | `MiniSparkline.jsx` exists; inline gauges/badges not in tables |
| 3A Scoreboard charts | — | `OptimizationScoreboard.jsx` is table-first |
| 3B Recommendations viz | — | List + severity views only |
| 3C Cost trends | Partial | Dashboard `monthly_trend` KPI + `CostTrendChart.jsx`; brush/compare overlay not built |
| 4A Virtual scroll | — | `react-window` not in `package.json` |
| 4B Drawer perf | — | Metrics load on drawer open today |
| 4C Request batching | Partial | `@tanstack/react-query` in use; no `/batch-lookup` endpoint |
| 4D Bundle/CSS | — | CRA (`react-scripts`); use `source-map-explorer` or CRA-compatible bundle analyzer |

**Build stack:** React 18 + CRA 5, custom CSS (`index.css`), Recharts 2.x → migrate to v3 during Phase 1 chart work (3A).

---

## Context

The Cost Optimizer Recommender frontend has strong foundations:
- 14 pages with clear purpose (dashboard, cost explorer, resource management, optimization actions)
- Custom CSS design system with theme variables (no framework dependency)
- New features recently added: OptimizationActions, OptimizationScoreboard, Azure Advisor integration
- 40+ React components following consistent patterns (FilterBar, PageHeader, ResourceInsightDrawer)
- Data fetching via custom hooks (useResourceSync, useOptimizationActions, useAdvisorIndex)

**Goals:** Modernize UX with better layouts, advanced interactivity, rich visualizations, and performance optimization.

---

## Solution: 4 strategic improvement areas

### 1. New layouts and reorganization

#### 1A: Responsive grid layouts
- **What:** Adaptive breakpoints replacing fixed-width design for tablet/mobile
- **Where:** All 14 pages, especially Dashboard, CostExplorer, ResourceList variants
- **How:**
  - Refactor `.main-content` padding and grid layouts using CSS custom properties for breakpoints
  - Create `ResponsiveTableWrapper.jsx` — intelligently switches table/card view on mobile
  - Create `ResponsiveHeroKpis.jsx` — stacks hero KPIs vertically on mobile
  - Update `.sidebar` to transform-slide on small screens (already partially done)
- **Complexity:** Medium (3–4 days)

#### 1B: Optimization hub unification
- **What:** Consolidate OptimizationActions + OptimizationScoreboard + RolloutMonitor into single cohesive hub with tab navigation
- **Where:** New `/optimization-hub` page, refactor `SidebarNav.jsx`
- **How:**
  - Create `OptimizationHub.jsx` with tabs: Actions, Scoreboard, Monitor
  - Route `/optimization/actions` → `/optimization-hub?tab=actions` (redirects)
  - Share context across tabs via `OptimizationHubContext`
- **Complexity:** Large (4–5 days)
- **Schedule:** Phase 3 (after responsive + performance wins)

#### 1C: Resource drawer reorganization
- **What:** Reorder `ResourceInsightDrawer` sections; add section collapse persistence
- **How:** Properties → Metrics → Findings → Cost drivers; `DrawerCollapsibleSection.jsx` + `usePersistedState`
- **Complexity:** Small (1 day)

---

### 2. Enhanced interactivity

#### 2A: Advanced filtering and sorting
- Extend `useFilterPresets`, `SortableTableHeader.jsx`, backend sort params on Actions + ResourceList + RunHistory
- **Complexity:** Medium (3–4 days)

#### 2B: Real-time updates via SSE
- `useServerEvents.js`, `GET /api/events/stream`, **polling fallback every 10s** (required)
- **Complexity:** Large (4–5 days BE + FE)
- **Infra:** Validate long-lived SSE through corporate reverse proxy before Phase 2 kickoff

#### 2C: Bulk operations expansion
- Extend `BulkActionBar` to Actions/Resources; optional bulk tag/assign APIs
- **Complexity:** Small (2 days)

#### 2D: Inline metric cards
- Extend `MiniSparkline.jsx`; `InlineGauge.jsx`, `InlineFindingBadge.jsx`
- **Complexity:** Medium (2–3 days)

---

### 3. Improved data visualization

#### 3A: Optimization scoreboard charts
- Tier pie, score histogram, dimension radar in `components/scoreboard/`; Recharts v3 migration here
- **Complexity:** Medium (3 days)

#### 3B: Recommendations visualization
- Bubble chart (primary); list view remains secondary tab
- **Complexity:** Medium (2–3 days)

#### 3C: Dashboard cost trends enhancement
- Period comparison overlay, interactive legend, brush on `CostTrendChart.jsx`
- **Complexity:** Small (1–2 days)

---

### 4. Performance optimizations

#### 4A: Table pagination and virtual scrolling
- `PaginationControls.jsx`, `VirtualizedTable.jsx`, add `react-window`
- **Complexity:** Medium (2–3 days)

#### 4B: Drawer performance
- Lazy sections, virtualized findings, batched metrics fetch
- **Complexity:** Medium (3 days)

#### 4C: Request batching
- `batchedQueries.js` + React Query dedup; `POST /api/batch-lookup` when needed
- **Complexity:** Large (3–4 days)

#### 4D: CSS and component optimization
- `React.memo`, split `index.css`, CRA bundle analysis, lazy admin routes
- **Complexity:** Small (1–2 days)

---

## Implementation roadmap

### Phase 1 (weeks 1–2): Foundation
| ID | Task | Owner | Est. |
|----|------|-------|------|
| 1A | Responsive layouts + `ResponsiveTableWrapper` | FE | 3–4d |
| 1C | Drawer reorder + collapsible sections | FE | 1d |
| 2A | Filters/sort/presets on Actions + ResourceList | FE | 3–4d |
| 3A | Scoreboard charts (+ Recharts v3) | FE | 3d |
| 3B | Recommendations bubble chart | FE | 2–3d |

**Deliverable:** Responsive pages; filterable/sortable Actions/Resources; scoreboard + recommendations charts

### Phase 2 (weeks 3–4): Interactivity and performance
| ID | Task | Owner | Est. |
|----|------|-------|------|
| 2B | SSE stream + polling fallback | BE + FE | 4–5d |
| 4A | Pagination + virtual scroll | FE | 2–3d |
| 4B | Drawer lazy-load + skeletons | FE | 3d |
| 4C | Batch lookup API + query layer | BE + FE | 3–4d |

**Deliverable:** Fast tables/drawers; fewer API calls; live job/action updates

### Phase 3 (weeks 5–6): Polish
| ID | Task | Owner | Est. |
|----|------|-------|------|
| 1B | Optimization hub unification | FE | 4–5d |
| 2C | Bulk ops expansion | FE + BE | 2d |
| 2D | Inline metrics in tables | FE | 2–3d |
| 4D | Bundle/CSS optimization | FE | 1–2d |
| 3C | Cost trends compare/brush | FE | 1–2d |

**Deliverable:** Unified optimization hub; performance targets met

---

## Success metrics

| Metric | Current | Target |
|--------|---------|--------|
| Page load | 3–4s | <2s |
| Drawer open | ~2s | <500ms |
| API requests (multi-resource) | 50+ | <30 |
| Bundle (gzipped) | ~600KB | <500KB |
| CLS | 0.15 | <0.1 |

---

## Acceptance criteria (release)

- [x] All primary pages usable at 375px width without horizontal page scroll (CSS pass; verify on device)
- [x] OptimizationActions support sort + saved presets
- [x] ResourceList support sort + saved presets
- [x] Scoreboard shows tier + score distribution charts
- [x] Drawer sections reordered with persisted collapse (Properties → Metrics → Findings → Cost drivers)
- [x] Drawer opens with skeleton; metrics lazy-load
- [x] Tables with 500+ rows remain interactive (virtual scroll or server pagination)
- [x] SSE or polling shows job progress without manual refresh
- [ ] Lighthouse performance score ≥85 on Dashboard and Resources
- [x] Recommendations chart view (bubble) alongside list/severity views

---

## Out of scope

- Adopting Tailwind, MUI, or another CSS framework
- Full redesign / rebrand
- Native mobile app

---

## Decisions (approval Jul 3, 2026)

| Question | Decision |
|----------|----------|
| Hub unification (1B) timing | **Phase 3** — keep `OptimizationHubLinks` until then |
| SSE + proxies | Ship with **polling fallback**; infra validation in Phase 2 week 1 |
| Recharts v3 | **Bundle with 3A** scoreboard charts |
| Jun 2026 UI spec | Partial work retained; open items tracked here |

---

## Implementation notes

Track progress by checking acceptance criteria above. Deviations must be noted in this section.

| Date | Note |
|------|------|
| Jul 3, 2026 | Spec approved; Phase 1 ready to start |
| Jul 3, 2026 | Phase 1: drawer reorder (1C), responsive KPIs/CSS (1A partial), Actions + ResourceList sort/presets (2A), scoreboard charts (3A), recommendations bubble chart (3B) |
| Jul 3, 2026 | Phase 2: `useServerEvents` + 10s polling fallback (2B), virtual scroll on Actions/Recommendations (4A), drawer skeletons + batch lookup (4B/4C) |
| Jul 3, 2026 | Phase 4: lazy-loaded Recharts chunks (dashboard daily cost, scoreboard, recommendations bubble), `chart-slot` CLS placeholders, 375px responsive pass (`overflow-x: clip`, hub tabs, bulk bar, filters), Optimization hub link in `OptimizationHubLinks` |

### Phase 4 (release hardening)

- [x] Code-split heavy chart bundles via `React.lazy` + `Suspense`
- [x] Chart CLS placeholders (`.chart-slot`)
- [x] 375px CSS pass on primary layouts (page shell, hub, filters, bulk bar, heroes)
- [ ] Lighthouse performance ≥85 on Dashboard and Resources — run against production build locally (see test plan below)
