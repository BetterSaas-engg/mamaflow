# Design — "Make items useful" (App polish, Track D · slice 1)

**Date:** 2026-07-04
**Status:** Approved (brainstorming) — pending implementation plan.
**Roadmap:** HANDOFF.md Track D ("App polish: calendar view, sync-progress UX, settings/delete-account"). This is slice 1 of Track D.

## Problem

The extraction pipeline captures rich per-item data — `date`, `time`, `location`,
`child_name`, `event_type`, `source_sender`, `source_email_link` — but the Flutter
home (`ui/home_screen.dart`) renders a single **flat, undifferentiated list** of every
item regardless of date or status, showing only title + a one-line subtitle. A parent
can't see "what's coming up this week", can't narrow to one child, and can't open the
email an item came from. `location` and `source_email_link` are fetched but never shown.
Completed/dismissed items are struck-through inline, cluttering the live view.

## Goal

Turn the flat list into an agenda a parent can act on: grouped by time, filterable by
child/type, with a tap-through detail that opens the source email.

## Scope

**In:**
1. Grouped agenda home (client-side time bucketing).
2. Filter chips (child + type), client-side over loaded items.
3. Item-detail screen with an "Open source email" action.
4. Backend: `?status=` filter on `GET /api/v1/items`; home defaults to open items with a "Show completed" toggle.

**Out (explicit non-goals):**
- Month **calendar** view (Track D fast-follow — option B from the layout brainstorm).
- Settings / sign-out relocation / delete-account (a later Track D slice).
- Push / reminders (Track B), any extraction or sync-pipeline change.

## Architecture

Frontend-heavy; one small, additive backend change. No new models, no migration.

```
GET /api/v1/items?status=open        ItemsController (Riverpod)
        │                                    │
        ▼                                    ▼
   list_items(status=…)  ──JSON──►  List<Item>  ──►  grouping + chip derivation (pure Dart)
   (ordering unchanged)                                     │
                                            ┌───────────────┼────────────────┐
                                            ▼               ▼                ▼
                                     Grouped agenda   Filter chips     Item detail
                                     (sectioned)      (client filter)  (url_launcher → Gmail)
```

### 1. Grouped agenda home

One scrolling list, sectioned by each item's `date` relative to the **device's local
today**. A pure function `groupItems(items, today) -> List<Section>`:

| Section        | Rule |
|----------------|------|
| **Overdue**    | `date` present and `< today`, status `open` |
| **Today**      | `date == today` |
| **This week**  | `today < date <= today + 7d` |
| **Later**      | `date > today + 7d` |
| **To-do — no date** | `date == null` (dateless actions) |

- Grouping is client-side — the dataset is bounded (~50 items/sync, one user). No pagination.
- Empty sections are omitted. Within a section, order follows the API (dated soonest-first,
  then `created_at`); `time` is a free-form string used only as a best-effort secondary sort.
- Rows keep the existing mark-done / dismiss popup menu and the event/action leading icon.
- Date parsing relies on the backend already normalizing `date` to ISO `YYYY-MM-DD`
  (`normalize_item_date`); a row whose `date` fails to parse is treated as dateless
  (falls into "To-do — no date") rather than crashing the group.

### 2. Filter chips

A horizontal chip row above the list, derived client-side from the currently-loaded items:
- **All** (default, selected) + one chip per distinct non-null `child_name` + one chip per
  distinct non-null `event_type`.
- **Single-select** for this slice: selecting a chip filters the visible items; tapping
  **All** clears. (Multi-select is a later refinement — YAGNI now.)
- Filtering happens over already-loaded data — **no per-chip network call**. Chips reflect
  only what's present; they appear/disappear as the underlying set changes.

### 3. Item-detail screen

Tapping a row pushes a detail route showing every populated field: title,
`action_required`, date + time, **location**, child, type, source sender, and status.
Primary action **"Open source email"** launches `source_email_link` (the server-stamped
Gmail deep link) via **`url_launcher`** (`mode: externalApplication`). If the link is
null/absent the button is hidden. Mark-done / dismiss are also available here and reflect
back to the list (shared controller state).

**New dependency:** `url_launcher` (pub.dev verified publisher, part of flutter.dev's
`packages/`). The only new dep in this slice.

### 4. Backend — `status` filter on `GET /items`

Add an optional `status` query param to the existing endpoint:

- `GET /api/v1/items?status=open|done|dismissed` — filters `Item.status`.
- Omitted → current behavior (all statuses), so existing callers are unaffected.
- Validated against the allowed set (`open`/`done`/`dismissed`); anything else → `422`.
- Ordering and the `from`/`to`/`type` filters are unchanged and compose with `status`.

The home fetches `status=open` by default; a **"Show completed"** toggle refetches with
`status=done` instead of over-fetching everything and hiding rows client-side. **Dismissed
items stay hidden** — dismissing is the user saying "not relevant", so they are not surfaced
by the toggle (reachable later via a dedicated view if ever needed). This is the one backend
touch — it reads the persistence layer, so it gets a security-audit pass per CLAUDE.md.

## Data flow & controller changes

- `ItemsController` gains a `statusFilter` (default `open`) that maps to the query param;
  `refresh()` and the post-sync refresh respect it.
- Grouping and chip derivation are **pure functions** in their own files
  (`items/grouping.dart`, `items/filters.dart`) so they unit-test without widgets.
- The detail screen reads a single `Item` (passed in via route args) — no new fetch.

## Error handling

- Backend: invalid `status` → `422` (FastAPI/Pydantic `Literal`); unchanged 404 path on PATCH.
- Frontend: unparseable `date` → item bucketed as dateless (never throws); a failed
  `url_launcher` (no mail client) shows a snackbar, doesn't crash; existing loading/error/
  empty states on the home are preserved.

## Testing

- **Backend (pytest):** `status=open|done|dismissed` returns only matching items; omitted
  returns all; invalid value → 422; composes with `type`/date filters; user isolation holds.
- **Frontend (flutter test):** `groupItems` bucketing incl. overdue, boundary (today, +7d),
  dateless, unparseable-date; chip derivation (distinct children/types, no nulls);
  single-select filter logic; detail screen renders fields and shows/hides the email button;
  "Show completed" flips the controller's status filter. Mock `ApiClient`, never live.
- `flutter analyze` clean; firewall-guard green (Dart patterns).

## Firewall / privacy invariants (unchanged)

- No item content, and nothing derived from it, touches the ad layer (D19). The ad SDK
  stays frontend-only and structurally isolated; this slice adds no ad-targeting surface.
- No raw email body is introduced anywhere (D5); the detail screen shows only already-
  extracted structured fields + the server-stamped Gmail link.
- The `status` filter is a read over existing persisted structured items — no new data
  stored, no token/PII handling touched (D4).

## Decisions taken

- **Completed items** → hidden from agenda groups, reachable via a "Show completed" toggle
  backed by the `status` filter (chosen over inline strike-through).
- **`url_launcher`** added so "Open source email" works (chosen over a display-only detail).
- **Grouped agenda (layout A) + filter chips (from layout C)** chosen over a month calendar
  (B) for the home; calendar deferred to a Track D fast-follow.
