# Design — Finish Track D: calendar tab + live sync progress (+ prose-date fix)

**Date:** 2026-07-04
**Status:** Approved (brainstorming) — pending implementation plan.
**Roadmap:** HANDOFF.md Track D. Final slices (slice 1 = useful-items view, slice 2 = settings + delete-account). This completes the autonomous Track D polish; the rest of the roadmap (B/E0/E/A1) is gated on account/console work.

## Problem

Three related gaps:
1. **Prose dates silently lose their date.** An item whose extracted `date` is prose with a bundled time (e.g. `"July 5th (Saturday) 10:00 AM"`) fails the ISO backstop (`normalize_item_date` parses date-only prose, but a trailing clock time breaks it), so the item falls into the agenda's "To-do — no date" bucket and would be invisible on a calendar. Items extracted before the ISO-date fix landed are also stored with prose dates.
2. **No calendar view.** The extracted events have dates but there's no month view — a parent can't see "what does this week/month look like."
3. **Opaque sync.** The first sync runs for minutes; the app shows only a static snackbar. The backend tracks counts but only fills them at the end.

## Goal

Dated items reliably carry an ISO date; a month calendar tab makes the schedule visible; and the sync shows live progress.

## Scope

**In:**
- **A0** — Prose-date fix: harden `normalize_item_date` to strip a bundled trailing time; a one-off idempotent backfill of existing items' `event_date`.
- **A** — Month calendar tab (bottom nav: Agenda | Calendar), dependency-free grid + dots + selected-day list + "Today" jump.
- **B** — Live sync progress: backend emits counts mid-run; the app shows a determinate progress card.

**Out (non-goals):** a calendar dependency (`table_calendar` etc.), week/day views, drag/reschedule, cross-month multi-select, per-child calendar colors, re-extraction of stored items (backfill re-normalizes the stored date string only — it does not call Claude).

## A0 — Prose dates land on the calendar

### A0a — Harden `normalize_item_date` (backend)

`normalize_item_date(value, email_date)` already coerces date-only prose (`"July 5th (Saturday)"` → `2026-07-05`) given an RFC-2822 `email_date`. It fails when a clock time is bundled into the date string. Add a step that strips a **trailing** time token before the existing parse — e.g. `" 10:00 AM"`, `" at 10am"`, `" 10:00"` — so `"July 5th (Saturday) 10:00 AM"` reduces to `"July 5th"` and then normalizes. Leave ISO values and the time-separated case untouched. Tests: the bundled-time variants normalize; ISO passes through; a genuinely unparseable value still returns unchanged (never throws).

### A0b — One-off backfill (backend, user-run)

A standalone idempotent script `python -m api.db.backfill_dates` (mirroring `python -m api.db.seed`): for every non-deleted `Item` whose `event_date` is non-null and **not** already ISO `YYYY-MM-DD`, recompute via the improved `normalize_item_date`, using the item's `created_at` formatted as an RFC-2822 date for the yearless-year reference. Write back only when the result changed to a valid ISO date; leave still-unparseable values as-is. Log counts (types/totals only, never values). Idempotent: a second run is a no-op. **Claude cannot write the shared Railway DB** (see memory `railway-migration-permission`) — the script is authored + tested here (against SQLite) and **run by the user** against Railway.

## A — Month calendar tab

**App shell.** New `HomeShell`: a `Scaffold` whose `bottomNavigationBar` is a `NavigationBar` with two destinations — **Agenda**, **Calendar** — and whose body is an `IndexedStack` (both tabs keep state). The auth gate shows `HomeShell` instead of `HomeScreen`. The current `HomeScreen` becomes the **Agenda** tab, unchanged (its own app bar, chips, sections, completed toggle, settings gear, and sync FAB all stay). Nested `Scaffold` per tab is intentional (per-tab app bar/FAB under a shared bottom nav — the standard Flutter pattern).

**Calendar tab (`CalendarScreen`).** Its own app bar: the month label + prev/next-month buttons + a **"Today"** action. Body: a hand-built **month grid** over the same `itemsProvider` (no refetch, no backend change):
- Pure `List<DateTime?> monthGrid(int year, int month)` → a flat list of 7-day weeks (whatever number of weeks the month spans, 4–6), with leading `null`s before the 1st and trailing `null`s after the last day so every week is full. Week starts Sunday.
- Pure `Map<String, List<Item>> itemsByDate(List<Item> items)` keyed by ISO `YYYY-MM-DD` (items whose `date` isn't ISO are simply absent — that's what A0 fixes).
- A day cell shows the day number; today is outlined; a day with items shows a **dot**. Tapping a day selects it; the selected day's items render in a list **below the grid**, reusing the existing item tile → tap → the existing `ItemDetailScreen`.
- State (`StatefulWidget`): visible `(year, month)` + selected `DateTime?`. Prev/next shift the month; "Today" jumps to the current month and selects today.
- Dateless to-dos are **not** shown here — they live in the Agenda tab's "To-do — no date" section (nothing lost).

Both pure helpers are unit-tested (month boundaries, leap February, dot days, day selection).

## B — Live sync progress

**Backend.** `SyncState` gains a `to_process: int | None` field (how many new emails will be extracted). `sync_state` gains `progress(user_id, *, messages_scanned, to_process, processed, items_created)` that updates the **running** state (does not change `status`). `_run_sync_job` calls it: once after metadata + classify + incremental-skip (`messages_scanned = len(metadata)`, `to_process = len(new_passed)`, `processed = 0`), then after each extracted email (`processed += 1`, running `items_created`). `SyncStatusResponse` + the state schema add `to_process`. The counts now populate during `running`; `finish`/`fail`/cooldown semantics are unchanged.

**Frontend.** A `SyncStatus` model (`status`, `messagesScanned`, `toProcess`, `processed`, `itemsCreated`, `error`) parsed from `GET /sync/status`. `SyncService` gains a `Stream<SyncStatus> run({pollInterval, maxPolls})` that POSTs `/sync` then polls, yielding each status until terminal (`done`/`failed`) — the existing 429-cooldown maps to a `SyncFailedException` as today. The **Agenda tab** renders a **progress card** while a sync is active (replacing the snackbar): a determinate `LinearProgressIndicator` (`processed / toProcess`) with live text — *"Scanned 30 · processed 12 / 28 · 3 items so far"* — falling back to indeterminate until `toProcess` is known. On `done`: refresh the list and show the final count briefly; on failure/429: the existing messages. `runUntilDone` is refactored into (or alongside) the stream so behavior is preserved.

## Error handling

- A0a never throws on bad input (returns unchanged). A0b skips values it can't normalize and is safe to re-run.
- Calendar: an item with a non-ISO/absent date is simply not placed (no crash); an empty month shows the grid with no dots; tapping an empty day shows an empty selected-day list.
- Sync stream: network error → surfaced as failure on the card; 429 → cooldown message; timeout (maxPolls) → the existing "timed out" message.

## Testing

- **A0a (pytest):** bundled-time variants (`"July 5th (Saturday) 10:00 AM"`, `"July 5 at 10am"`) → ISO; ISO passthrough; unparseable → unchanged.
- **A0b (pytest, SQLite):** a seeded item with a prose `event_date` is rewritten to ISO using its `created_at` year; an ISO item is left untouched; a second run is a no-op; an unparseable value is left as-is.
- **A (flutter):** `monthGrid` (Jan/Dec boundaries, leap Feb 2028, cell count); `itemsByDate` (grouping, non-ISO excluded); calendar renders dots on item days, selecting a day lists its items, "Today" selects today, prev/next change the month.
- **B (pytest):** `_run_sync_job` updates `processed`/`items_created`/`to_process` mid-run (assert via a monkeypatched extractor that checks state between items); `/sync/status` returns them during `running`. **(flutter):** `SyncStatus.fromJson`; the stream yields running→done from a fake client; the progress card renders live counts and the determinate bar.
- `flutter analyze` clean; backend + frontend suites green; firewall-guard green.

## Firewall / privacy invariants

- **D19:** no content or derivation reaches the ad layer; the calendar and progress card read only already-loaded structured items / status counts. No ad surface added.
- **D5:** no raw email body introduced; A0b re-normalizes only the stored `event_date` string, never re-fetches or re-extracts.
- **D4:** no token/PII handling touched.
- Security-auditor still runs (A0/backfill touch data persistence; B touches the sync pipeline) — expected PASS.

## Decisions taken

- Calendar is **dependency-free** (hand-built grid), week starts **Sunday**, with a **"Today"** jump — no calendar library, no week/day view.
- Bottom-nav **tabs** (Agenda | Calendar); dateless to-dos stay in Agenda.
- Sync progress uses **live backend counts** (determinate bar), not a frontend-only spinner.
- The date backfill is a **user-run script** (DB-write permission boundary), not an automatic migration.
