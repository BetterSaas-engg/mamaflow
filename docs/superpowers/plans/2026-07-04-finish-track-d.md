# Finish Track D — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make prose dates land on a new month calendar tab, and show live sync progress.

**Architecture:** Three components. **A0** hardens the backend date normalizer for bundled times + a user-run backfill of stored items. **A** adds a bottom-nav Calendar tab (dependency-free month grid over the already-loaded items). **B** has the sync background job emit counts mid-run and the app render a determinate progress card.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async + Pydantic v2 (backend); Flutter + Riverpod + Dio + mocktail. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-07-04-finish-track-d-design.md`

## Global Constraints

- No new dependency (no calendar library). Calendar week starts **Sunday**.
- Backend: run from `backend/`; tests `./.venv/bin/python -m pytest -q` (venv python, never system).
- `normalize_item_date` never throws on bad input (returns the value unchanged). The date backfill is **idempotent** and re-normalizes only the stored `event_date` string — it never re-fetches or re-extracts (D5). Claude cannot write the shared Railway DB — the backfill is a `python -m api.db.backfill_dates` script the **user** runs.
- Live sync counts: the background job updates the **running** state; `finish`/`fail`/cooldown semantics are unchanged.
- Frontend: `flutter test` + `flutter analyze` clean; mock `ApiClient`/services, never live.
- Firewall (D19): calendar + progress card read only already-loaded structured items / status counts — no ad surface, no content to the ad layer. No token/PII handling touched (D4).
- TDD every task. Commit after each; Conventional Commits; end each commit body with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: Backend — normalize a bundled trailing time (A0a)

**Files:**
- Modify: `backend/api/services/ai_extractor.py` (`normalize_item_date`, add a regex constant)
- Test: `backend/tests/test_extraction_dates.py`

**Interfaces:**
- Consumes: existing `normalize_item_date(value, email_date)` and its `_PARENTHETICAL`/`_ORDINAL`/`_ISO_DATE`/`_DATE_FORMATS_*` machinery.
- Produces: `normalize_item_date` now strips a trailing clock time (requiring a colon or am/pm, so a bare day number is never eaten) before parsing.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_extraction_dates.py` (uses `normalize_item_date` directly; add the import if not present: `from api.services.ai_extractor import normalize_item_date`):

```python
_RFC = "Tue, 01 Jul 2026 09:00:00 -0400"


def test_normalize_strips_bundled_time():
    assert normalize_item_date("July 5th (Saturday) 10:00 AM", _RFC) == "2026-07-05"
    assert normalize_item_date("July 5 at 10am", _RFC) == "2026-07-05"
    assert normalize_item_date("January 5, 2026 3:30pm", _RFC) == "2026-01-05"


def test_normalize_does_not_eat_bare_day():
    # No time token -> the day number must survive.
    assert normalize_item_date("July 5", _RFC) == "2026-07-05"


def test_normalize_iso_and_unparseable_unchanged():
    assert normalize_item_date("2026-07-05", _RFC) == "2026-07-05"
    assert normalize_item_date("sometime next week", _RFC) == "sometime next week"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_extraction_dates.py -q -k "bundled or bare_day or unparseable"`
Expected: FAIL — the bundled-time cases return the value unchanged (trailing time breaks the parse).

- [ ] **Step 3: Add the trailing-time strip**

In `backend/api/services/ai_extractor.py`, add the regex next to the other date constants (after `_ORDINAL` at line ~45):

```python
# A trailing clock time bundled into a date string ("July 5 10:00 AM").
# Requires a colon or am/pm so a bare day number is never mistaken for a time.
_TRAILING_TIME = re.compile(
    r"\s+(?:at\s+)?\d{1,2}(?::\d{2})?\s*(?:am|pm)\s*$|\s+(?:at\s+)?\d{1,2}:\d{2}\s*$",
    re.IGNORECASE,
)
```

Then in `normalize_item_date`, apply it in the cleaning block — after the existing collapse line `cleaned = " ".join(cleaned.split())` (line ~69), add:

```python
    cleaned = _TRAILING_TIME.sub("", cleaned).strip()
```

- [ ] **Step 4: Run tests to verify they pass + full suite**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_extraction_dates.py -q && ./.venv/bin/python -m pytest -q`
Expected: PASS; full suite green.

- [ ] **Step 5: Commit**

```bash
git add backend/api/services/ai_extractor.py backend/tests/test_extraction_dates.py
git commit -m "fix(backend): normalize dates with a bundled trailing time

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Backend — one-off date backfill script (A0b)

**Files:**
- Create: `backend/api/db/backfill_dates.py`
- Test: `backend/tests/test_backfill_dates.py`

**Interfaces:**
- Consumes: `normalize_item_date` (Task 1), `Item` (`api.models.item.Item`), `AsyncSessionLocal` (`api.db.session`).
- Produces: `async backfill_item_dates(db) -> int` (rewrites non-ISO `event_date` values to ISO in place, returns the count fixed; idempotent) + a `python -m api.db.backfill_dates` entrypoint.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_backfill_dates.py`:

```python
"""Backfill of existing items' prose event_date -> ISO (A0b)."""

from sqlalchemy import select

from api.db.backfill_dates import backfill_item_dates
from api.models.item import Item
from api.services.users import get_or_create_user


async def _add_item(db, user, event_date):
    item = Item(
        user_id=user.id, message_id="m", item_type="event",
        event_title="Soccer", event_date=event_date,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def test_backfill_rewrites_prose_date_to_iso(db):
    user = await get_or_create_user(db, "p@x.com")
    item = await _add_item(db, user, "July 5th (Saturday) 10:00 AM")

    fixed = await backfill_item_dates(db)

    await db.refresh(item)
    # created_at is ~now (2026) -> the yearless date resolves to that year.
    assert item.event_date == f"{item.created_at.year}-07-05"
    assert fixed == 1


async def test_backfill_leaves_iso_and_unparseable_untouched(db):
    user = await get_or_create_user(db, "p@x.com")
    iso = await _add_item(db, user, "2026-07-05")
    bad = await _add_item(db, user, "sometime soon")

    fixed = await backfill_item_dates(db)

    await db.refresh(iso)
    await db.refresh(bad)
    assert iso.event_date == "2026-07-05"   # already ISO -> untouched
    assert bad.event_date == "sometime soon"  # unparseable -> untouched
    assert fixed == 0  # neither item was a fixable prose date


async def test_backfill_is_idempotent(db):
    user = await get_or_create_user(db, "p@x.com")
    await _add_item(db, user, "July 5th (Saturday)")

    first = await backfill_item_dates(db)
    second = await backfill_item_dates(db)

    assert first == 1
    assert second == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_backfill_dates.py -q`
Expected: FAIL (3 tests) — `api.db.backfill_dates` doesn't exist.

- [ ] **Step 3: Write the backfill module**

Create `backend/api/db/backfill_dates.py`:

```python
"""Re-normalize existing items' event_date to ISO YYYY-MM-DD. Idempotent.

Items extracted before the ISO-date fix (or with a bundled time) carry a prose
event_date that the agenda/calendar can't place. This re-runs the normalizer
over the stored string only — it never re-fetches or re-extracts the email.

Usage: python -m api.db.backfill_dates
"""

import asyncio
import email.utils
import logging
import re

from sqlalchemy import select

from api.db.session import AsyncSessionLocal
from api.models.item import Item
from api.services.ai_extractor import normalize_item_date

_log = logging.getLogger(__name__)
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


async def backfill_item_dates(db) -> int:
    """Rewrite non-ISO event_date values to ISO in place. Returns the count
    fixed. Uses each item's created_at as the year reference for yearless
    prose dates. Idempotent: values already ISO or still unparseable are left
    untouched."""
    result = await db.execute(
        select(Item).where(Item.event_date.is_not(None), Item.deleted_at.is_(None))
    )
    fixed = 0
    for item in result.scalars().all():
        current = item.event_date
        if _ISO.match(current):
            continue
        ref = email.utils.format_datetime(item.created_at)
        normalized = normalize_item_date(current, ref)
        if normalized and _ISO.match(normalized) and normalized != current:
            item.event_date = normalized
            fixed += 1
    await db.commit()
    _log.info("date backfill: %d item(s) normalized", fixed)
    return fixed


async def _main() -> None:
    async with AsyncSessionLocal() as db:
        n = await backfill_item_dates(db)
        print(f"backfilled {n} item date(s)")


if __name__ == "__main__":
    asyncio.run(_main())
```

- [ ] **Step 4: Run tests to verify they pass + full suite**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_backfill_dates.py -q && ./.venv/bin/python -m pytest -q`
Expected: 3 tests PASS; full suite green.

- [ ] **Step 5: Commit**

```bash
git add backend/api/db/backfill_dates.py backend/tests/test_backfill_dates.py
git commit -m "feat(backend): idempotent date backfill script (prose event_date -> ISO)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Backend — live sync progress (B1)

**Files:**
- Modify: `backend/api/services/sync_state.py` (`SyncState`, add `progress`)
- Modify: `backend/api/schemas/email.py` (`SyncStatusResponse`)
- Modify: `backend/api/routers/sync.py` (`_run_sync_job`, `get_sync_status`)
- Test: `backend/tests/test_sync_api.py`

**Interfaces:**
- Consumes: existing `sync_state` (`get_state`/`try_start`/`finish`/`fail`), `_run_sync_job`.
- Produces: `SyncState.to_process: int | None`; `sync_state.progress(user_id, *, messages_scanned, to_process, processed, items_created)` (updates the running state, keeps `status="running"`); `SyncStatusResponse.to_process`; `_run_sync_job` reports progress before and during the loop.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_sync_api.py` (it already has `_user_with_token`, `_auth`, and monkeypatches `sync_router.fetch_recent_metadata` etc. — match that style; `sync_router` is `api.routers.sync`):

```python
async def test_sync_status_reports_to_process_during_run(client, db, monkeypatch):
    from api.services import sync_state
    from api.services.users import get_or_create_user
    # _user_with_token creates the user "parent@example.com"; re-fetch it so we
    # can seed a running state under the same id the JWT names.
    user = await get_or_create_user(db, "parent@example.com")
    _, token = await _user_with_token(db)
    sync_state.progress(user.id, messages_scanned=30, to_process=28, processed=12, items_created=3)

    resp = await client.get("/api/v1/sync/status", headers=_auth(token))

    body = resp.json()
    assert body["status"] == "running"
    assert body["to_process"] == 28
    assert body["processed"] == 12
    assert body["items_created"] == 3


async def test_run_sync_job_updates_processed_incrementally(db, session_factory, monkeypatch):
    # session_factory is the conftest fixture bound to the TEST SQLite engine
    # (a StaticPool shared with `db`), so the job sees the committed test user.
    # Do NOT use the production get_session_factory() — it binds to Railway.
    from api.services import sync_state
    from api.routers import sync as sync_router
    from api.services.users import get_or_create_user
    from api.schemas.family_event import FamilyItem, ExtractionResponse

    user = await get_or_create_user(db, "inc@example.com")
    meta = [
        {"message_id": "a", "sender": "s@school.edu", "subject": "x", "date": ""},
        {"message_id": "b", "sender": "s@school.edu", "subject": "y", "date": ""},
    ]
    monkeypatch.setattr(sync_router, "fetch_recent_metadata", lambda email: meta)
    monkeypatch.setattr(sync_router, "fetch_message_bodies", lambda email, ids: {i: "body" for i in ids})
    # s@school.edu is not on the default blocklist, so both messages pass classify.

    # Record processed at each extract call to prove it increments mid-run.
    seen = []

    def fake_extract(*args, **kwargs):
        seen.append(sync_state.get_state(user.id).processed)
        return ExtractionResponse(events=[FamilyItem(item_type="action", action_required="do")])

    monkeypatch.setattr(sync_router, "extract_events", fake_extract)

    sync_state.try_start(user.id)
    await sync_router._run_sync_job(user.id, user.email, session_factory)

    # processed was 0 before the first item, 1 before the second.
    assert seen == [0, 1]
    final = sync_state.get_state(user.id)
    assert final.status == "done"
    assert final.to_process == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_sync_api.py -q -k "to_process or incrementally"`
Expected: FAIL — `sync_state.progress` and `to_process` don't exist.

- [ ] **Step 3: Add `to_process` + `progress` to sync_state**

In `backend/api/services/sync_state.py`, add the field to the `SyncState` dataclass (alongside `processed`):

```python
    to_process: int | None = None
```

Add a `progress` function (after `try_start`, before `finish`):

```python
def progress(
    user_id: uuid.UUID,
    *,
    messages_scanned: int,
    to_process: int,
    processed: int,
    items_created: int,
) -> None:
    """Update the running state with live counts (status stays 'running')."""
    _states[user_id] = SyncState(
        status="running",
        messages_scanned=messages_scanned,
        to_process=to_process,
        processed=processed,
        items_created=items_created,
    )
```

- [ ] **Step 4: Add `to_process` to the status schema + endpoint**

In `backend/api/schemas/email.py`, add to `SyncStatusResponse` (after `processed`):

```python
    to_process: int | None = None
```

In `backend/api/routers/sync.py`, `get_sync_status` builds `SyncStatusResponse(...)` — add `to_process=state.to_process` to that constructor call.

- [ ] **Step 5: Report progress from the background job**

In `backend/api/routers/sync.py` `_run_sync_job`, right after `new_passed` is computed and bodies are fetched (before the `items_created = 0` loop), add:

```python
            sync_state.progress(
                user_id,
                messages_scanned=len(metadata),
                to_process=len(new_passed),
                processed=0,
                items_created=0,
            )
```

Change the loop to enumerate and report after each item. Replace the existing `for msg, _status in new_passed:` loop header with `for _i, (msg, _status) in enumerate(new_passed):` and, right after `items_created += len(saved)`, add:

```python
                sync_state.progress(
                    user_id,
                    messages_scanned=len(metadata),
                    to_process=len(new_passed),
                    processed=_i + 1,
                    items_created=items_created,
                )
```

`sync_state.finish(...)` at the end is unchanged.

- [ ] **Step 6: Run tests to verify they pass + full suite**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_sync_api.py -q && ./.venv/bin/python -m pytest -q`
Expected: PASS; full suite green.

- [ ] **Step 7: Commit**

```bash
git add backend/api/services/sync_state.py backend/api/schemas/email.py backend/api/routers/sync.py backend/tests/test_sync_api.py
git commit -m "feat(backend): live sync progress (to_process + incremental processed)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Frontend — calendar math (monthGrid + itemsByDate)

**Files:**
- Create: `frontend/lib/calendar/calendar_math.dart`
- Test: `frontend/test/calendar/calendar_math_test.dart`

**Interfaces:**
- Consumes: `Item` (`items/item.dart`, field `date` is `String?`).
- Produces:
  - `List<DateTime?> monthGrid(int year, int month)` — flat list of full 7-day weeks (Sunday-start), `null` padding before the 1st and after the last day.
  - `Map<String, List<Item>> itemsByDate(List<Item> items)` — items keyed by their ISO `YYYY-MM-DD` `date`; non-ISO/null dates excluded.

- [ ] **Step 1: Write the failing test**

Create `frontend/test/calendar/calendar_math_test.dart`:

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/calendar/calendar_math.dart';
import 'package:mamaflow/items/item.dart';

Item _item(String id, {String? date}) =>
    Item(id: id, itemType: 'event', status: 'open', eventTitle: id, date: date);

void main() {
  test('monthGrid pads to full weeks, Sunday-start', () {
    // July 2026: the 1st is a Wednesday (weekday 3) -> 3 leading nulls.
    final grid = monthGrid(2026, 7);
    expect(grid.length % 7, 0);
    expect(grid.take(3).every((d) => d == null), isTrue);
    expect(grid[3]!.day, 1);
    final days = grid.where((d) => d != null).toList();
    expect(days.length, 31);
    expect(days.last!.day, 31);
  });

  test('monthGrid handles leap February', () {
    final days = monthGrid(2028, 2).where((d) => d != null).toList();
    expect(days.length, 29);
  });

  test('itemsByDate groups ISO dates and excludes non-ISO/null', () {
    final map = itemsByDate([
      _item('a', date: '2026-07-05'),
      _item('b', date: '2026-07-05'),
      _item('c', date: 'July 5th'),
      _item('d'),
    ]);
    expect(map['2026-07-05']!.map((i) => i.id), ['a', 'b']);
    expect(map.containsKey('July 5th'), isFalse);
    expect(map.length, 1);
  });
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && flutter test test/calendar/calendar_math_test.dart`
Expected: FAIL — `calendar_math.dart` doesn't exist.

- [ ] **Step 3: Implement the math**

Create `frontend/lib/calendar/calendar_math.dart`:

```dart
import '../items/item.dart';

/// A month laid out as consecutive full weeks (Sunday-start). Cells before the
/// 1st and after the last day are null. Length is always a multiple of 7.
List<DateTime?> monthGrid(int year, int month) {
  final first = DateTime(year, month, 1);
  final daysInMonth = DateTime(year, month + 1, 0).day; // day 0 of next month
  final lead = first.weekday % 7; // DateTime: Mon=1..Sun=7 -> Sun=0..Sat=6
  final cells = <DateTime?>[];
  for (var i = 0; i < lead; i++) {
    cells.add(null);
  }
  for (var d = 1; d <= daysInMonth; d++) {
    cells.add(DateTime(year, month, d));
  }
  while (cells.length % 7 != 0) {
    cells.add(null);
  }
  return cells;
}

final _iso = RegExp(r'^\d{4}-\d{2}-\d{2}$');

/// Groups items by their ISO `YYYY-MM-DD` date. Items with a null or non-ISO
/// date are excluded (they live in the agenda's "To-do — no date" section).
Map<String, List<Item>> itemsByDate(List<Item> items) {
  final map = <String, List<Item>>{};
  for (final item in items) {
    final date = item.date;
    if (date != null && _iso.hasMatch(date)) {
      (map[date] ??= <Item>[]).add(item);
    }
  }
  return map;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && flutter test test/calendar/calendar_math_test.dart`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/calendar/calendar_math.dart frontend/test/calendar/calendar_math_test.dart
git commit -m "feat(frontend): calendar month-grid + itemsByDate helpers

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Frontend — CalendarScreen

**Files:**
- Create: `frontend/lib/ui/calendar_screen.dart`
- Test: `frontend/test/calendar/calendar_screen_test.dart`

**Interfaces:**
- Consumes: `monthGrid`/`itemsByDate` (Task 4), `itemsProvider` (`items/items_controller.dart`), `Item`, `ItemDetailScreen` (`ui/item_detail_screen.dart`).
- Produces: `CalendarScreen` (ConsumerStatefulWidget) — month grid with dots, prev/next + Today, tap-a-day lists that day's items → detail.

- [ ] **Step 1: Write the failing test**

Create `frontend/test/calendar/calendar_screen_test.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/core/providers.dart';
import 'package:mamaflow/items/item.dart';
import 'package:mamaflow/items/items_controller.dart';
import 'package:mamaflow/items/items_service.dart';
import 'package:mamaflow/ui/calendar_screen.dart';
import 'package:mocktail/mocktail.dart';

class _MockService extends Mock implements ItemsService {}

Item _item(String id, {required String date}) =>
    Item(id: id, itemType: 'event', status: 'open', eventTitle: id, date: date);

Widget _host(ItemsService svc) => ProviderScope(
      overrides: [itemsServiceProvider.overrideWithValue(svc)],
      child: const MaterialApp(home: CalendarScreen()),
    );

void main() {
  setUpAll(() => registerFallbackValue('open'));

  testWidgets('shows the current month and lists a tapped day\'s items',
      (tester) async {
    final now = DateTime.now();
    final iso =
        '${now.year.toString().padLeft(4, '0')}-${now.month.toString().padLeft(2, '0')}-${now.day.toString().padLeft(2, '0')}';
    final svc = _MockService();
    when(() => svc.list(status: any(named: 'status')))
        .thenAnswer((_) async => [_item('Soccer', date: iso)]);

    await tester.pumpWidget(_host(svc));
    await tester.pumpAndSettle();

    // Tap today's cell (day number is rendered as text).
    await tester.tap(find.text('${now.day}').first);
    await tester.pumpAndSettle();

    expect(find.text('Soccer'), findsOneWidget);
  });
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && flutter test test/calendar/calendar_screen_test.dart`
Expected: FAIL — `calendar_screen.dart` doesn't exist.

- [ ] **Step 3: Implement the screen**

Create `frontend/lib/ui/calendar_screen.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../calendar/calendar_math.dart';
import '../items/item.dart';
import '../items/items_controller.dart';
import 'item_detail_screen.dart';

const _monthNames = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

String _iso(DateTime d) =>
    '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

bool _sameDay(DateTime a, DateTime b) =>
    a.year == b.year && a.month == b.month && a.day == b.day;

/// Month calendar over the loaded items: dots on days with items, tap a day to
/// list its items. Dateless to-dos stay in the Agenda tab.
class CalendarScreen extends ConsumerStatefulWidget {
  const CalendarScreen({super.key});
  @override
  ConsumerState<CalendarScreen> createState() => _CalendarScreenState();
}

class _CalendarScreenState extends ConsumerState<CalendarScreen> {
  late DateTime _visible; // first of the visible month
  DateTime? _selected;

  @override
  void initState() {
    super.initState();
    final now = DateTime.now();
    _visible = DateTime(now.year, now.month);
    _selected = DateTime(now.year, now.month, now.day);
  }

  void _shiftMonth(int delta) => setState(() {
        _visible = DateTime(_visible.year, _visible.month + delta);
      });

  void _today() => setState(() {
        final now = DateTime.now();
        _visible = DateTime(now.year, now.month);
        _selected = DateTime(now.year, now.month, now.day);
      });

  @override
  Widget build(BuildContext context) {
    final items = ref.watch(itemsProvider);
    return Scaffold(
      appBar: AppBar(
        title: Text('${_monthNames[_visible.month - 1]} ${_visible.year}'),
        actions: [
          IconButton(
            tooltip: 'Previous month',
            icon: const Icon(Icons.chevron_left),
            onPressed: () => _shiftMonth(-1),
          ),
          IconButton(
            tooltip: 'Next month',
            icon: const Icon(Icons.chevron_right),
            onPressed: () => _shiftMonth(1),
          ),
          TextButton(onPressed: _today, child: const Text('Today')),
        ],
      ),
      body: items.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (_, _) => const Center(child: Text('Could not load items.')),
        data: (list) => _calendar(context, list),
      ),
    );
  }

  Widget _calendar(BuildContext context, List<Item> list) {
    final byDate = itemsByDate(list);
    final cells = monthGrid(_visible.year, _visible.month);
    final today = DateTime.now();
    final selectedItems =
        _selected == null ? const <Item>[] : (byDate[_iso(_selected!)] ?? const <Item>[]);

    return Column(
      children: [
        const _WeekdayHeader(),
        GridView.count(
          crossAxisCount: 7,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          children: [
            for (final cell in cells)
              if (cell == null)
                const SizedBox.shrink()
              else
                _DayCell(
                  day: cell.day,
                  isToday: _sameDay(cell, today),
                  isSelected: _selected != null && _sameDay(cell, _selected!),
                  hasItems: byDate.containsKey(_iso(cell)),
                  onTap: () => setState(() => _selected = cell),
                ),
          ],
        ),
        const Divider(height: 1),
        Expanded(
          child: selectedItems.isEmpty
              ? const Center(child: Text('No items on this day.'))
              : ListView.separated(
                  itemCount: selectedItems.length,
                  separatorBuilder: (_, _) => const Divider(height: 1),
                  itemBuilder: (context, i) => _DayItemTile(item: selectedItems[i]),
                ),
        ),
      ],
    );
  }
}

class _WeekdayHeader extends StatelessWidget {
  const _WeekdayHeader();
  @override
  Widget build(BuildContext context) => Row(
        children: [
          for (final d in const ['S', 'M', 'T', 'W', 'T', 'F', 'S'])
            Expanded(
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 6),
                child: Text(d,
                    textAlign: TextAlign.center,
                    style: const TextStyle(fontSize: 11, color: Colors.grey)),
              ),
            ),
        ],
      );
}

class _DayCell extends StatelessWidget {
  const _DayCell({
    required this.day,
    required this.isToday,
    required this.isSelected,
    required this.hasItems,
    required this.onTap,
  });
  final int day;
  final bool isToday;
  final bool isSelected;
  final bool hasItems;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return InkWell(
      onTap: onTap,
      child: Container(
        decoration: BoxDecoration(
          color: isSelected ? scheme.primaryContainer : null,
          border: isToday ? Border.all(color: scheme.primary) : null,
          borderRadius: BorderRadius.circular(8),
        ),
        margin: const EdgeInsets.all(2),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text('$day'),
            const SizedBox(height: 2),
            Container(
              width: 6,
              height: 6,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: hasItems ? scheme.primary : Colors.transparent,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _DayItemTile extends StatelessWidget {
  const _DayItemTile({required this.item});
  final Item item;

  @override
  Widget build(BuildContext context) {
    final subtitle = <String>[
      if (item.time != null) item.time!,
      if (item.eventType != null) item.eventType!,
      if (item.childName != null) item.childName!,
    ].join('  ·  ');
    return ListTile(
      leading: Icon(item.isEvent ? Icons.event : Icons.check_circle_outline),
      title: Text(item.title),
      subtitle: subtitle.isEmpty ? null : Text(subtitle),
      onTap: () => Navigator.of(context).push(
        MaterialPageRoute(builder: (_) => ItemDetailScreen(item: item)),
      ),
    );
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && flutter test test/calendar/calendar_screen_test.dart`
Expected: PASS.

- [ ] **Step 5: Analyze + commit**

Run: `cd frontend && flutter analyze`
Expected: no issues.

```bash
git add frontend/lib/ui/calendar_screen.dart frontend/test/calendar/calendar_screen_test.dart
git commit -m "feat(frontend): month calendar screen (dots + day detail + Today)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Frontend — HomeShell bottom nav (Agenda | Calendar)

**Files:**
- Create: `frontend/lib/ui/home_shell.dart`
- Modify: `frontend/lib/app.dart` (`AuthGate` shows `HomeShell`)
- Test: `frontend/test/ui/home_shell_test.dart`

**Interfaces:**
- Consumes: `HomeScreen` (`ui/home_screen.dart`), `CalendarScreen` (Task 5).
- Produces: `HomeShell` (StatefulWidget) — a `NavigationBar` (Agenda | Calendar) over an `IndexedStack`. `AuthGate` renders `HomeShell` when signed in.

- [ ] **Step 1: Write the failing test**

Create `frontend/test/ui/home_shell_test.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/core/providers.dart';
import 'package:mamaflow/items/item.dart';
import 'package:mamaflow/items/items_controller.dart';
import 'package:mamaflow/items/items_service.dart';
import 'package:mamaflow/ui/home_shell.dart';
import 'package:mocktail/mocktail.dart';

class _MockService extends Mock implements ItemsService {}

void main() {
  setUpAll(() => registerFallbackValue('open'));

  testWidgets('has Agenda + Calendar tabs and switches to the calendar',
      (tester) async {
    final svc = _MockService();
    when(() => svc.list(status: any(named: 'status')))
        .thenAnswer((_) async => <Item>[]);

    await tester.pumpWidget(ProviderScope(
      overrides: [itemsServiceProvider.overrideWithValue(svc)],
      child: const MaterialApp(home: HomeShell()),
    ));
    await tester.pumpAndSettle();

    expect(find.text('Agenda'), findsOneWidget);
    expect(find.text('Calendar'), findsWidgets);

    await tester.tap(find.text('Calendar').last);
    await tester.pumpAndSettle();

    // The calendar app bar shows the current month/year title.
    final now = DateTime.now();
    const months = ['January','February','March','April','May','June','July','August','September','October','November','December'];
    expect(find.text('${months[now.month - 1]} ${now.year}'), findsOneWidget);
  });
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && flutter test test/ui/home_shell_test.dart`
Expected: FAIL — `home_shell.dart` doesn't exist.

- [ ] **Step 3: Implement the shell**

Create `frontend/lib/ui/home_shell.dart`:

```dart
import 'package:flutter/material.dart';

import 'calendar_screen.dart';
import 'home_screen.dart';

/// Signed-in shell: a bottom nav switching between the Agenda (grouped list)
/// and the month Calendar. IndexedStack keeps each tab's state.
class HomeShell extends StatefulWidget {
  const HomeShell({super.key});
  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _index = 0;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(
        index: _index,
        children: const [HomeScreen(), CalendarScreen()],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.list_alt), label: 'Agenda'),
          NavigationDestination(icon: Icon(Icons.calendar_month), label: 'Calendar'),
        ],
      ),
    );
  }
}
```

- [ ] **Step 4: Point the auth gate at HomeShell**

In `frontend/lib/app.dart`: change the import `import 'ui/home_screen.dart';` to `import 'ui/home_shell.dart';` and change the `AuthGate` signed-in branch from `const HomeScreen()` to `const HomeShell()`.

- [ ] **Step 5: Run tests + full suite + analyze**

Run: `cd frontend && flutter test test/ui/home_shell_test.dart && flutter test && flutter analyze`
Expected: shell test PASS; full suite green; analyze clean.

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/ui/home_shell.dart frontend/lib/app.dart frontend/test/ui/home_shell_test.dart
git commit -m "feat(frontend): bottom-nav shell (Agenda | Calendar)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Frontend — live sync progress card

**Files:**
- Modify: `frontend/lib/items/sync_service.dart` (`SyncStatus`, `run` stream; refactor `runUntilDone`)
- Modify: `frontend/lib/ui/home_screen.dart` (progress card replaces the snackbar in `_sync`)
- Test: `frontend/test/items/sync_service_test.dart` (add), `frontend/test/items/home_screen_test.dart` (keep green)

**Interfaces:**
- Consumes: `ApiClient` (`postJson`/`getJson`), `syncServiceProvider`, `itemsProvider`.
- Produces:
  - `class SyncStatus { status, messagesScanned, toProcess, processed, itemsCreated, error; fromJson }`.
  - `Stream<SyncStatus> SyncService.run({pollInterval, maxPolls})` — POSTs `/sync` then polls `/sync/status`, yielding each status until `done`/`failed`; 429 → `SyncFailedException`; exhausted polls → timeout `SyncFailedException`.
  - `runUntilDone` reimplemented on top of `run` (returns final `itemsCreated`) so existing callers/tests are unaffected.

- [ ] **Step 1: Write the failing tests**

Add to `frontend/test/items/sync_service_test.dart`:

```dart
test('run yields running statuses then done', () async {
  final api = _MockApi();
  when(() => api.postJson(any(), any())).thenAnswer((_) async => {'status': 'started'});
  final statuses = [
    {'status': 'running', 'processed': 1, 'to_process': 3, 'items_created': 0},
    {'status': 'running', 'processed': 3, 'to_process': 3, 'items_created': 2},
    {'status': 'done', 'items_created': 2, 'processed': 3, 'to_process': 3},
  ];
  when(() => api.getJson(any())).thenAnswer((_) async => statuses.removeAt(0));

  final seen = await SyncService(api).run(pollInterval: Duration.zero).toList();

  expect(seen.map((s) => s.status), ['running', 'running', 'done']);
  expect(seen[0].processed, 1);
  expect(seen[0].toProcess, 3);
  expect(seen.last.itemsCreated, 2);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && flutter test test/items/sync_service_test.dart -p vm --plain-name "run yields"`
(If the name filter is awkward, just run the file.) Expected: FAIL — `SyncStatus`/`run` don't exist.

- [ ] **Step 3: Add SyncStatus + run(), refactor runUntilDone**

Replace the body of `frontend/lib/items/sync_service.dart` (keep the `SyncFailedException` class) with:

```dart
import 'package:dio/dio.dart';

import '../core/api_client.dart';

class SyncFailedException implements Exception {
  const SyncFailedException(this.message);
  final String message;
  @override
  String toString() => 'SyncFailedException: $message';
}

/// A point-in-time view of the server-side sync, parsed from GET /sync/status.
class SyncStatus {
  const SyncStatus({
    required this.status,
    this.messagesScanned,
    this.toProcess,
    this.processed,
    this.itemsCreated,
    this.error,
  });

  final String status; // idle | running | done | failed
  final int? messagesScanned;
  final int? toProcess;
  final int? processed;
  final int? itemsCreated;
  final String? error;

  factory SyncStatus.fromJson(Map<String, dynamic> j) => SyncStatus(
        status: j['status'] as String? ?? 'idle',
        messagesScanned: (j['messages_scanned'] as num?)?.toInt(),
        toProcess: (j['to_process'] as num?)?.toInt(),
        processed: (j['processed'] as num?)?.toInt(),
        itemsCreated: (j['items_created'] as num?)?.toInt(),
        error: j['error'] as String?,
      );
}

/// Triggers a server-side inbox sync and polls it to completion.
class SyncService {
  SyncService(this._api);
  final ApiClient _api;

  /// Starts a sync and yields each polled status until it finishes. Throws
  /// [SyncFailedException] on a cooldown (429) or timeout.
  Stream<SyncStatus> run({
    Duration pollInterval = const Duration(seconds: 2),
    int maxPolls = 90,
  }) async* {
    try {
      await _api.postJson('/api/v1/sync', const <String, dynamic>{});
    } on DioException catch (e) {
      if (e.response?.statusCode == 429) {
        throw const SyncFailedException('Synced recently — try again in a minute.');
      }
      rethrow;
    }
    for (var i = 0; i < maxPolls; i++) {
      if (pollInterval > Duration.zero) {
        await Future<void>.delayed(pollInterval);
      }
      final status = SyncStatus.fromJson(await _api.getJson('/api/v1/sync/status'));
      yield status;
      if (status.status == 'done' || status.status == 'failed') return;
    }
    throw const SyncFailedException('Sync timed out. Pull to refresh later.');
  }

  /// Drains [run] and returns the number of newly created items; throws
  /// [SyncFailedException] on server-reported failure or timeout.
  Future<int> runUntilDone({
    Duration pollInterval = const Duration(seconds: 2),
    int maxPolls = 90,
  }) async {
    var created = 0;
    await for (final s in run(pollInterval: pollInterval, maxPolls: maxPolls)) {
      if (s.status == 'failed') {
        throw SyncFailedException(s.error ?? 'Sync failed. Try again.');
      }
      created = s.itemsCreated ?? created;
    }
    return created;
  }
}
```

- [ ] **Step 4: Render a progress card in the Agenda `_sync`**

In `frontend/lib/ui/home_screen.dart`, add a nullable field to `_HomeScreenState` (next to `_child`/`_type`/`_completed`):

```dart
  SyncStatus? _syncStatus; // non-null while a sync is in flight
```

Replace the `_sync` method body with the stream-driven version (keeps the same messenger + refresh + failure handling):

```dart
  Future<void> _sync(BuildContext context) async {
    final messenger = ScaffoldMessenger.of(context);
    setState(() => _syncStatus = const SyncStatus(status: 'running'));
    try {
      await for (final s in ref.read(syncServiceProvider).run()) {
        if (s.status == 'failed') {
          throw SyncFailedException(s.error ?? 'Sync failed. Try again.');
        }
        setState(() => _syncStatus = s);
      }
      final created = _syncStatus?.itemsCreated ?? 0;
      await ref.read(itemsProvider.notifier).refresh();
      setState(() => _syncStatus = null);
      messenger.showSnackBar(SnackBar(content: Text('Synced — $created new item(s)')));
    } on SyncFailedException catch (e) {
      setState(() => _syncStatus = null);
      messenger.showSnackBar(SnackBar(content: Text(e.message)));
    } catch (_) {
      setState(() => _syncStatus = null);
      messenger.showSnackBar(const SnackBar(content: Text('Sync failed. Try again.')));
    }
  }
```

Add a progress-card widget above the list. In the `build` method's `body`, wrap the existing `items.when(...)` result in a `Column` with the card on top when a sync is active. Concretely, change the `body:` to:

```dart
      body: Column(
        children: [
          if (_syncStatus != null) _SyncProgressCard(status: _syncStatus!),
          Expanded(
            child: items.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => _Centered(
                message: 'Could not load items.',
                actionLabel: 'Retry',
                onAction: () => ref.read(itemsProvider.notifier).refresh(),
              ),
              data: (list) => RefreshIndicator(
                onRefresh: () => ref.read(itemsProvider.notifier).refresh(),
                child: _body(list),
              ),
            ),
          ),
        ],
      ),
```

Add the card widget at the bottom of the file:

```dart
class _SyncProgressCard extends StatelessWidget {
  const _SyncProgressCard({required this.status});
  final SyncStatus status;

  @override
  Widget build(BuildContext context) {
    final total = status.toProcess;
    final done = status.processed;
    final value = (total != null && total > 0 && done != null) ? done / total : null;
    final line = total == null
        ? 'Syncing your inbox…'
        : 'Scanned ${status.messagesScanned ?? 0} · processed ${done ?? 0} / $total · ${status.itemsCreated ?? 0} items';
    return Card(
      margin: const EdgeInsets.all(12),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(line, style: const TextStyle(fontSize: 12)),
            const SizedBox(height: 8),
            LinearProgressIndicator(value: value),
          ],
        ),
      ),
    );
  }
}
```

Ensure `home_screen.dart` imports `SyncStatus` — it already imports `../items/sync_service.dart` (which now exports `SyncStatus`), so no new import is needed. Confirm the `_sync` call site still passes `context` (the FAB `onPressed: () => _sync(context)`).

- [ ] **Step 5: Run tests + full suite + analyze + firewall**

Run: `cd frontend && flutter test && flutter analyze && cd .. && bash scripts/firewall-guard.sh`
Expected: all green (existing `sync_service_test` runUntilDone cases still pass via the refactor; `home_screen_test` still passes); analyze clean; firewall exit 0.

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/items/sync_service.dart frontend/lib/ui/home_screen.dart frontend/test/items/sync_service_test.dart
git commit -m "feat(frontend): live sync progress card (determinate bar + counts)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: Security audit + HANDOFF

**Files:**
- Modify: `HANDOFF.md`

- [ ] **Step 1: Security audit**

Dispatch `@security-auditor` on the feature diff. Focus: the backfill (A0b) mutates only the stored `event_date` string, is user-scoped by nothing sensitive (it re-normalizes a date format across all items — confirm it never re-fetches/re-extracts and touches no PII/token/body); the sync-progress change only writes in-process counters (no content, no ad surface); the calendar + progress card read already-loaded structured items only (D19/D5 clean). Address any BLOCK before proceeding.

- [ ] **Step 2: Update HANDOFF Track D row**

In `HANDOFF.md`, extend the Track D row: slices 3 (calendar tab + live sync progress + prose-date fix) shipped; note the user must run `python -m api.db.backfill_dates` against Railway to fix already-stored prose dates; Track D is now complete.

- [ ] **Step 3: Commit + push**

```bash
git add HANDOFF.md
git commit -m "docs: HANDOFF — Track D calendar + live sync progress + date backfill

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push
```

---

## Self-review notes

- **Spec coverage:** A0a normalizer (Task 1), A0b backfill (Task 2), B1 backend progress (Task 3), calendar math (Task 4), CalendarScreen (Task 5), HomeShell + gate (Task 6), B2 progress card (Task 7), audit + HANDOFF (Task 8). Dependency-free calendar, Sunday-start, Today jump, dateless-in-Agenda all honored.
- **Type consistency:** `normalize_item_date`, `backfill_item_dates(db)`, `sync_state.progress(...)`, `to_process`, `monthGrid`/`itemsByDate`, `CalendarScreen`, `HomeShell`, `SyncStatus`/`SyncService.run`/`runUntilDone` are used with identical signatures across tasks.
- **Backfill test note:** Task 2 Step 4 explicitly corrects the second test's `fixed` assertion to `0` — do not skip that edit.
