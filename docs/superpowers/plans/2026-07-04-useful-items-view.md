# Useful Items View — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the flat items list into a grouped agenda with child/type filter chips and a tap-through detail screen that opens the source email; add a `status` filter to the items API so the home shows open items with a "Show completed" toggle.

**Architecture:** Frontend-heavy. One additive backend change (a `status` query param on `GET /api/v1/items`). Grouping and chip derivation are pure Dart functions in their own files; the detail screen takes an injected URL opener for testability. No new DB models, no migration.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async + Pydantic v2 (backend); Flutter + Riverpod + Dio + mocktail; new dependency `url_launcher`.

**Spec:** `docs/superpowers/specs/2026-07-04-useful-items-view-design.md`

## Global Constraints

- Backend: run from `backend/`; tests `./.venv/bin/python -m pytest -q`. Async SQLAlchemy session, awaited. Pydantic schemas at boundaries. UUID PKs, soft-delete (`deleted_at IS NULL`) — the existing `list_items` already honors this.
- `GET /api/v1/items` with **no** `status` param must keep returning all statuses (existing callers unaffected).
- Item ordering is unchanged: `event_date IS NULL` last, then `event_date`, then `created_at`.
- Frontend: `flutter test` + `flutter analyze` must stay clean. Mock `ApiClient`/services — never hit live APIs.
- Firewall (D19): no item content or derivation reaches the ad layer; this slice adds no ad-targeting surface. No raw email body anywhere (D5). The `status` filter is a read over existing structured items (D4 untouched).
- Section titles (verbatim): `Overdue`, `Today`, `This week`, `Later`, `To-do — no date`.
- "Show completed" surfaces `status=done` only; dismissed items stay hidden.
- Commit after each task with Conventional Commits; end messages with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: Backend — `status` filter on `GET /api/v1/items`

**Files:**
- Modify: `backend/api/services/items.py` (`list_items`, lines ~75-98)
- Modify: `backend/api/routers/items.py` (`get_items`, lines ~15-25)
- Test: `backend/tests/test_items_api.py`

**Interfaces:**
- Consumes: `list_items(db, user, date_from=None, date_to=None, item_type=None)` (existing).
- Produces: `list_items(..., status: str | None = None)` — when set, filters `Item.status == status`. Router accepts `status: Literal["open","done","dismissed"] | None = Query(None)`; invalid value → 422.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_items_api.py`:

```python
async def test_get_items_filters_by_status(client, db):
    user, token = await _user_with_token(db)
    await persist_items(
        db, user, "m1",
        [FamilyItem(item_type="event", event_title="Soccer", date="2026-06-20")],
    )
    await persist_items(
        db, user, "m2",
        [FamilyItem(item_type="action", action_required="RSVP")],
    )
    # Mark the second item done.
    listed = (await client.get("/api/v1/items", headers=_auth(token))).json()["items"]
    action = next(i for i in listed if i["item_type"] == "action")
    await client.patch(f"/api/v1/items/{action['id']}",
                       headers=_auth(token), json={"status": "done"})

    open_only = await client.get("/api/v1/items?status=open", headers=_auth(token))
    done_only = await client.get("/api/v1/items?status=done", headers=_auth(token))
    all_items = await client.get("/api/v1/items", headers=_auth(token))

    assert [i["item_type"] for i in open_only.json()["items"]] == ["event"]
    assert [i["item_type"] for i in done_only.json()["items"]] == ["action"]
    assert len(all_items.json()["items"]) == 2  # omitted => unchanged


async def test_get_items_rejects_invalid_status(client, db):
    _, token = await _user_with_token(db)
    resp = await client.get("/api/v1/items?status=bogus", headers=_auth(token))
    assert resp.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_items_api.py -q -k status`
Expected: FAIL — `status=open` currently returns both items (no filter); `status=bogus` returns 200 not 422.

- [ ] **Step 3: Add the `status` param to `list_items`**

In `backend/api/services/items.py`, change the signature and add the filter:

```python
async def list_items(
    db: AsyncSession,
    user: User,
    date_from: str | None = None,
    date_to: str | None = None,
    item_type: str | None = None,
    status: str | None = None,
) -> list[Item]:
    """List a user's non-deleted items, newest event first.

    Date filters compare on event_date; ISO 'YYYY-MM-DD' strings sort
    lexicographically, so range comparison is correct.
    """
    query = select(Item).where(Item.user_id == user.id, Item.deleted_at.is_(None))

    if item_type is not None:
        query = query.where(Item.item_type == item_type)
    if status is not None:
        query = query.where(Item.status == status)
    if date_from is not None:
        query = query.where(Item.event_date >= date_from)
    if date_to is not None:
        query = query.where(Item.event_date <= date_to)

    query = query.order_by(Item.event_date.is_(None), Item.event_date, Item.created_at)
    result = await db.execute(query)
    return list(result.scalars().all())
```

- [ ] **Step 4: Add the `status` query param to the router**

In `backend/api/routers/items.py`, add the `Literal` import and the param. Update the top imports and `get_items`:

```python
from typing import Literal

# ... existing imports ...


@router.get("", response_model=ItemListResponse)
async def get_items(
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None, alias="to"),
    type: str | None = Query(None),
    status: Literal["open", "done", "dismissed"] | None = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items = await list_items(
        db, user, date_from=from_, date_to=to, item_type=type, status=status
    )
    return ItemListResponse(items=[item_to_read(i) for i in items])
```

- [ ] **Step 5: Run tests to verify they pass + full suite**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_items_api.py -q -k status && ./.venv/bin/python -m pytest -q`
Expected: PASS; full suite green (72+ passed).

- [ ] **Step 6: Commit**

```bash
git add backend/api/services/items.py backend/api/routers/items.py backend/tests/test_items_api.py
git commit -m "feat(backend): status filter on GET /items (open/done/dismissed)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Frontend — `groupItems` date bucketing (pure function)

**Files:**
- Create: `frontend/lib/items/grouping.dart`
- Test: `frontend/test/items/grouping_test.dart`

**Interfaces:**
- Consumes: `Item` (`frontend/lib/items/item.dart`) — fields `date` (`String?`, ISO `YYYY-MM-DD` or null).
- Produces:
  - `class ItemSection { final String title; final List<Item> items; }`
  - `List<ItemSection> groupItems(List<Item> items, DateTime today)` — buckets by date relative to `today` (date-only), sections in fixed order, empty sections omitted, input order preserved within a bucket. Unparseable/absent date → `To-do — no date`.

- [ ] **Step 1: Write the failing test**

Create `frontend/test/items/grouping_test.dart`:

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/items/item.dart';
import 'package:mamaflow/items/grouping.dart';

Item _item(String id, {String? date}) =>
    Item(id: id, itemType: 'event', status: 'open', eventTitle: id, date: date);

void main() {
  final today = DateTime(2026, 7, 4); // Saturday

  test('buckets items into date-relative sections in fixed order', () {
    final sections = groupItems([
      _item('overdue', date: '2026-07-01'),
      _item('today', date: '2026-07-04'),
      _item('thisweek', date: '2026-07-09'),
      _item('later', date: '2026-08-01'),
      _item('nodate'),
    ], today);

    expect(sections.map((s) => s.title).toList(),
        ['Overdue', 'Today', 'This week', 'Later', 'To-do — no date']);
    expect(sections[0].items.single.id, 'overdue');
    expect(sections[4].items.single.id, 'nodate');
  });

  test('boundary: today+7 is This week, today+8 is Later', () {
    final sections = groupItems([
      _item('edge7', date: '2026-07-11'),
      _item('edge8', date: '2026-07-12'),
    ], today);
    final byTitle = {for (final s in sections) s.title: s.items};
    expect(byTitle['This week']!.single.id, 'edge7');
    expect(byTitle['Later']!.single.id, 'edge8');
  });

  test('omits empty sections and treats unparseable date as no-date', () {
    final sections = groupItems([_item('bad', date: 'not-a-date')], today);
    expect(sections.map((s) => s.title).toList(), ['To-do — no date']);
    expect(sections.single.items.single.id, 'bad');
  });
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && flutter test test/items/grouping_test.dart`
Expected: FAIL — `grouping.dart` doesn't exist (compile error).

- [ ] **Step 3: Implement `groupItems`**

Create `frontend/lib/items/grouping.dart`:

```dart
import 'item.dart';

/// A titled bucket of items for the grouped agenda home.
class ItemSection {
  const ItemSection(this.title, this.items);
  final String title;
  final List<Item> items;
}

/// Buckets [items] by their `date` relative to [today] (date-only). Sections
/// come back in fixed order with empty ones omitted; input order is preserved
/// within a bucket (the API already sorts soonest-first). An absent or
/// unparseable date falls into "To-do — no date".
List<ItemSection> groupItems(List<Item> items, DateTime today) {
  final day = DateTime(today.year, today.month, today.day);
  final weekEnd = day.add(const Duration(days: 7));

  final overdue = <Item>[];
  final todayList = <Item>[];
  final thisWeek = <Item>[];
  final later = <Item>[];
  final noDate = <Item>[];

  for (final item in items) {
    final parsed = _parseDate(item.date);
    if (parsed == null) {
      noDate.add(item);
    } else if (parsed.isBefore(day)) {
      overdue.add(item);
    } else if (parsed.isAtSameMomentAs(day)) {
      todayList.add(item);
    } else if (!parsed.isAfter(weekEnd)) {
      thisWeek.add(item);
    } else {
      later.add(item);
    }
  }

  return [
    if (overdue.isNotEmpty) ItemSection('Overdue', overdue),
    if (todayList.isNotEmpty) ItemSection('Today', todayList),
    if (thisWeek.isNotEmpty) ItemSection('This week', thisWeek),
    if (later.isNotEmpty) ItemSection('Later', later),
    if (noDate.isNotEmpty) ItemSection('To-do — no date', noDate),
  ];
}

DateTime? _parseDate(String? raw) {
  if (raw == null) return null;
  final parsed = DateTime.tryParse(raw); // ISO 'YYYY-MM-DD' -> midnight
  if (parsed == null) return null;
  return DateTime(parsed.year, parsed.month, parsed.day);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && flutter test test/items/grouping_test.dart`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/items/grouping.dart frontend/test/items/grouping_test.dart
git commit -m "feat(frontend): groupItems date bucketing for the agenda view

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Frontend — filter chip derivation + apply (pure functions)

**Files:**
- Create: `frontend/lib/items/filters.dart`
- Test: `frontend/test/items/filters_test.dart`

**Interfaces:**
- Consumes: `Item` (fields `childName`, `eventType`, both `String?`).
- Produces:
  - `List<String> childValues(List<Item> items)` — distinct non-null `childName`, sorted.
  - `List<String> typeValues(List<Item> items)` — distinct non-null `eventType`, sorted.
  - `List<Item> applyChipFilter(List<Item> items, {String? child, String? type})` — at most one of `child`/`type` is non-null (single-select); returns matching items, or all when both null.

- [ ] **Step 1: Write the failing test**

Create `frontend/test/items/filters_test.dart`:

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/items/item.dart';
import 'package:mamaflow/items/filters.dart';

Item _item(String id, {String? child, String? type}) => Item(
    id: id, itemType: 'event', status: 'open', eventTitle: id,
    childName: child, eventType: type);

void main() {
  final items = [
    _item('a', child: 'Emma', type: 'medical'),
    _item('b', child: 'Charlie', type: 'school'),
    _item('c', child: 'Emma', type: 'school'),
    _item('d'), // no child/type
  ];

  test('derives distinct sorted child and type values, nulls excluded', () {
    expect(childValues(items), ['Charlie', 'Emma']);
    expect(typeValues(items), ['medical', 'school']);
  });

  test('applyChipFilter by child', () {
    expect(applyChipFilter(items, child: 'Emma').map((i) => i.id), ['a', 'c']);
  });

  test('applyChipFilter by type', () {
    expect(applyChipFilter(items, type: 'school').map((i) => i.id), ['b', 'c']);
  });

  test('applyChipFilter with no selection returns all', () {
    expect(applyChipFilter(items).length, 4);
  });
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && flutter test test/items/filters_test.dart`
Expected: FAIL — `filters.dart` doesn't exist.

- [ ] **Step 3: Implement the filter functions**

Create `frontend/lib/items/filters.dart`:

```dart
import 'item.dart';

/// Distinct, sorted, non-null child names present in [items].
List<String> childValues(List<Item> items) => _distinct(items.map((i) => i.childName));

/// Distinct, sorted, non-null event types present in [items].
List<String> typeValues(List<Item> items) => _distinct(items.map((i) => i.eventType));

/// Single-select chip filter: at most one of [child]/[type] is set. Returns the
/// matching items, or all of [items] when neither is set.
List<Item> applyChipFilter(List<Item> items, {String? child, String? type}) {
  if (child != null) return items.where((i) => i.childName == child).toList();
  if (type != null) return items.where((i) => i.eventType == type).toList();
  return items;
}

List<String> _distinct(Iterable<String?> values) {
  final set = values.whereType<String>().toSet().toList()..sort();
  return set;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && flutter test test/items/filters_test.dart`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/items/filters.dart frontend/test/items/filters_test.dart
git commit -m "feat(frontend): filter chip derivation + single-select apply

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Frontend — status filter through service + controller

**Files:**
- Modify: `frontend/lib/items/items_service.dart` (`list`)
- Modify: `frontend/lib/items/items_controller.dart` (`ItemsController`)
- Test: `frontend/test/items/items_service_test.dart`, `frontend/test/items/items_controller_test.dart` (new)

**Interfaces:**
- Consumes: `ApiClient.getJson(path, {query})`, `itemsServiceProvider`.
- Produces:
  - `ItemsService.list({String? from, String? to, String? type, String? status})` — passes `status` as a query param.
  - `ItemsController` gains `showCompleted(bool)` which flips its status filter (`open` ↔ `done`) and refreshes; `build()`/`refresh()` fetch with the current filter. Default `open`.

- [ ] **Step 1: Write the failing tests**

Add to `frontend/test/items/items_service_test.dart` (a `status` case; keep existing tests):

```dart
test('list passes status as a query param', () async {
  final api = _MockApi();
  when(() => api.getJson(any(), query: any(named: 'query')))
      .thenAnswer((_) async => {'items': []});
  final svc = ItemsService(api);

  await svc.list(status: 'done');

  final captured = verify(() => api.getJson('/api/v1/items',
      query: captureAny(named: 'query'))).captured.single as Map;
  expect(captured['status'], 'done');
});
```

Create `frontend/test/items/items_controller_test.dart`:

```dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/core/providers.dart';
import 'package:mamaflow/items/item.dart';
import 'package:mamaflow/items/items_controller.dart';
import 'package:mamaflow/items/items_service.dart';
import 'package:mocktail/mocktail.dart';

class _MockService extends Mock implements ItemsService {}

void main() {
  test('defaults to status=open, then showCompleted switches to done', () async {
    final svc = _MockService();
    when(() => svc.list(status: any(named: 'status')))
        .thenAnswer((_) async => <Item>[]);

    final container = ProviderContainer(overrides: [
      itemsServiceProvider.overrideWithValue(svc),
    ]);
    addTearDown(container.dispose);

    await container.read(itemsProvider.future); // triggers build()
    await container.read(itemsProvider.notifier).showCompleted(true);

    verify(() => svc.list(status: 'open')).called(1);
    verify(() => svc.list(status: 'done')).called(1);
  });
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && flutter test test/items/items_service_test.dart test/items/items_controller_test.dart`
Expected: FAIL — `list` has no `status` param; `showCompleted` undefined.

- [ ] **Step 3: Add `status` to `ItemsService.list`**

In `frontend/lib/items/items_service.dart`, extend the signature and query:

```dart
  Future<List<Item>> list({String? from, String? to, String? type, String? status}) async {
    final query = <String, dynamic>{
      'from': ?from,
      'to': ?to,
      'type': ?type,
      'status': ?status,
    };
    final resp = await _api.getJson(
      '/api/v1/items',
      query: query.isEmpty ? null : query,
    );
    final raw = (resp['items'] as List?) ?? const [];
    return raw
        .map((e) => Item.fromJson(Map<String, dynamic>.from(e as Map)))
        .toList(growable: false);
  }
```

- [ ] **Step 4: Add the status filter to `ItemsController`**

Replace the `ItemsController` class body in `frontend/lib/items/items_controller.dart`:

```dart
/// Loads the user's items and exposes mutations. Fetches open items by default;
/// [showCompleted] flips to done items ("Show completed" toggle on the home).
class ItemsController extends AsyncNotifier<List<Item>> {
  String _status = 'open';

  String get statusFilter => _status;

  @override
  Future<List<Item>> build() => ref.read(itemsServiceProvider).list(status: _status);

  Future<void> refresh() async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(
        () => ref.read(itemsServiceProvider).list(status: _status));
  }

  /// Toggle between open items (false) and completed/done items (true).
  Future<void> showCompleted(bool completed) async {
    _status = completed ? 'done' : 'open';
    await refresh();
  }

  Future<void> setStatus(String id, String status) async {
    await ref.read(itemsServiceProvider).updateStatus(id, status);
    await refresh();
  }
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && flutter test test/items/items_service_test.dart test/items/items_controller_test.dart`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/items/items_service.dart frontend/lib/items/items_controller.dart frontend/test/items/items_service_test.dart frontend/test/items/items_controller_test.dart
git commit -m "feat(frontend): status filter through service + controller (open/completed)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Frontend — item detail screen + `url_launcher`

**Files:**
- Modify: `frontend/pubspec.yaml` (add `url_launcher`)
- Create: `frontend/lib/ui/item_detail_screen.dart`
- Test: `frontend/test/items/item_detail_screen_test.dart`

**Interfaces:**
- Consumes: `Item`, `itemsProvider` (for mark done/dismiss via `setStatus`).
- Produces:
  - `class ItemDetailScreen extends ConsumerWidget` with `const ItemDetailScreen({required this.item, this.opener})`.
  - `typedef UrlOpener = Future<bool> Function(String url);` — injectable; defaults to a `url_launcher` call. The "Open source email" button is shown only when `item.sourceEmailLink != null`.

- [ ] **Step 1: Add the dependency**

Run: `cd frontend && flutter pub add url_launcher`
Expected: `pubspec.yaml` gains `url_launcher: ^6.x`; `flutter pub get` succeeds.

- [ ] **Step 2: Write the failing test**

Create `frontend/test/items/item_detail_screen_test.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/items/item.dart';
import 'package:mamaflow/ui/item_detail_screen.dart';

Item _item({String? link}) => Item(
      id: '1', itemType: 'event', status: 'open',
      eventTitle: 'Dentist', date: '2026-07-08', time: '10:00 AM',
      location: 'Grandview', childName: 'Emma', eventType: 'medical',
      sourceEmailLink: link,
    );

Widget _host(Item item, {UrlOpener? opener}) => ProviderScope(
      child: MaterialApp(home: ItemDetailScreen(item: item, opener: opener)),
    );

void main() {
  testWidgets('shows item fields', (tester) async {
    await tester.pumpWidget(_host(_item(link: 'https://mail.google.com/x')));
    expect(find.text('Dentist'), findsOneWidget);
    expect(find.text('Grandview'), findsOneWidget);
    expect(find.text('Emma'), findsOneWidget);
  });

  testWidgets('Open source email launches the link', (tester) async {
    String? opened;
    await tester.pumpWidget(_host(_item(link: 'https://mail.google.com/x'),
        opener: (url) async { opened = url; return true; }));
    await tester.tap(find.text('Open source email'));
    await tester.pump();
    expect(opened, 'https://mail.google.com/x');
  });

  testWidgets('hides the button when there is no source link', (tester) async {
    await tester.pumpWidget(_host(_item(link: null)));
    expect(find.text('Open source email'), findsNothing);
  });
}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd frontend && flutter test test/items/item_detail_screen_test.dart`
Expected: FAIL — `item_detail_screen.dart` doesn't exist.

- [ ] **Step 4: Implement the detail screen**

Create `frontend/lib/ui/item_detail_screen.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../items/item.dart';
import '../items/items_controller.dart';

/// Opens a URL in an external app; returns whether it launched. Injectable so
/// widget tests don't hit the platform channel.
typedef UrlOpener = Future<bool> Function(String url);

Future<bool> _defaultOpener(String url) =>
    launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);

/// Full detail for one item: every populated field + an "Open source email"
/// action (Gmail deep link) + mark done/dismiss.
class ItemDetailScreen extends ConsumerWidget {
  const ItemDetailScreen({super.key, required this.item, UrlOpener? opener})
      : opener = opener ?? _defaultOpener;

  final Item item;
  final UrlOpener opener;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final rows = <(String, String?)>[
      ('When', [item.date, item.time].whereType<String>().join(' ')),
      ('Location', item.location),
      ('Child', item.childName),
      ('Type', item.eventType),
      ('To do', item.actionRequired),
      ('From', item.sourceSender),
      ('Status', item.status),
    ];
    final link = item.sourceEmailLink;

    return Scaffold(
      appBar: AppBar(title: Text(item.title)),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(item.title, style: Theme.of(context).textTheme.headlineSmall),
          const SizedBox(height: 16),
          for (final (label, value) in rows)
            if (value != null && value.isNotEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 6),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SizedBox(width: 96, child: Text(label,
                        style: const TextStyle(color: Colors.grey))),
                    Expanded(child: Text(value)),
                  ],
                ),
              ),
          const SizedBox(height: 24),
          if (link != null)
            FilledButton.icon(
              icon: const Icon(Icons.mail_outline),
              label: const Text('Open source email'),
              onPressed: () async {
                final ok = await opener(link);
                if (!ok && context.mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text('Could not open the email.')),
                  );
                }
              },
            ),
          if (item.status == 'open') ...[
            const SizedBox(height: 8),
            OverflowBar(
              children: [
                TextButton(
                  onPressed: () {
                    ref.read(itemsProvider.notifier).setStatus(item.id, 'done');
                    Navigator.of(context).pop();
                  },
                  child: const Text('Mark done'),
                ),
                TextButton(
                  onPressed: () {
                    ref.read(itemsProvider.notifier).setStatus(item.id, 'dismissed');
                    Navigator.of(context).pop();
                  },
                  child: const Text('Dismiss'),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && flutter test test/items/item_detail_screen_test.dart`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add frontend/pubspec.yaml frontend/pubspec.lock frontend/lib/ui/item_detail_screen.dart frontend/test/items/item_detail_screen_test.dart
git commit -m "feat(frontend): item detail screen with open-source-email (url_launcher)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Frontend — rebuild the home as a grouped, filterable agenda

**Files:**
- Modify: `frontend/lib/ui/home_screen.dart`
- Test: `frontend/test/items/home_screen_test.dart`

**Interfaces:**
- Consumes: `groupItems` (Task 2), `childValues`/`typeValues`/`applyChipFilter` (Task 3), `ItemsController.showCompleted` (Task 4), `ItemDetailScreen` (Task 5), `itemsProvider`, `sessionProvider`, `syncServiceProvider`.
- Produces: a `HomeScreen` that renders section headers, a filter-chip row, tappable rows that push `ItemDetailScreen`, and a "Show completed" toggle. The `_sync` snackbar flow is unchanged.

- [ ] **Step 1: Write the failing test**

Replace `frontend/test/items/home_screen_test.dart` with (keeps the empty-state case, adds grouping + chips):

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/core/providers.dart';
import 'package:mamaflow/items/item.dart';
import 'package:mamaflow/items/items_controller.dart';
import 'package:mamaflow/items/items_service.dart';
import 'package:mamaflow/ui/home_screen.dart';
import 'package:mocktail/mocktail.dart';

class _MockService extends Mock implements ItemsService {}

Item _item(String id, {String? date, String? child}) => Item(
    id: id, itemType: 'event', status: 'open', eventTitle: id,
    date: date, childName: child);

Widget _host(ItemsService svc) => ProviderScope(
      overrides: [itemsServiceProvider.overrideWithValue(svc)],
      child: const MaterialApp(home: HomeScreen()),
    );

void main() {
  setUpAll(() => registerFallbackValue('open'));

  testWidgets('renders section headers and chips', (tester) async {
    final svc = _MockService();
    when(() => svc.list(status: any(named: 'status'))).thenAnswer((_) async => [
      _item('nodate', child: 'Emma'),
      _item('later', date: '2026-12-31', child: 'Charlie'),
    ]);

    await tester.pumpWidget(_host(svc));
    await tester.pumpAndSettle();

    expect(find.text('Later'), findsOneWidget);
    expect(find.text('To-do — no date'), findsOneWidget);
    expect(find.widgetWithText(FilterChip, 'Emma'), findsOneWidget);
    expect(find.widgetWithText(FilterChip, 'Charlie'), findsOneWidget);
  });

  testWidgets('shows empty state when there are no items', (tester) async {
    final svc = _MockService();
    when(() => svc.list(status: any(named: 'status')))
        .thenAnswer((_) async => <Item>[]);

    await tester.pumpWidget(_host(svc));
    await tester.pumpAndSettle();

    expect(find.textContaining('No items'), findsOneWidget);
  });
}
```

(The mock-service override lets the real `ItemsController` build; `pumpAndSettle` lets the async provider resolve before assertions.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && flutter test test/items/home_screen_test.dart`
Expected: FAIL — no section headers / `FilterChip`s in the current flat list.

- [ ] **Step 3: Rebuild `home_screen.dart`**

Replace `frontend/lib/ui/home_screen.dart` with:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../auth/session_controller.dart';
import '../items/filters.dart';
import '../items/grouping.dart';
import '../items/item.dart';
import '../items/items_controller.dart';
import '../items/sync_service.dart';
import 'item_detail_screen.dart';

/// The signed-in home: the user's items as a grouped agenda (Overdue / Today /
/// This week / Later / To-do), filterable by child/type, with a "Show
/// completed" toggle. Rows tap through to [ItemDetailScreen].
class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});
  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen> {
  String? _child; // single-select chip: one of child/type is set at a time
  String? _type;
  bool _completed = false;

  @override
  Widget build(BuildContext context) {
    final items = ref.watch(itemsProvider);
    return Scaffold(
      floatingActionButton: FloatingActionButton.extended(
        icon: const Icon(Icons.sync),
        label: const Text('Sync inbox'),
        onPressed: () => _sync(context),
      ),
      appBar: AppBar(
        title: const Text('Mamaflow'),
        actions: [
          IconButton(
            tooltip: _completed ? 'Show open' : 'Show completed',
            icon: Icon(_completed ? Icons.inbox : Icons.done_all),
            onPressed: () {
              setState(() => _completed = !_completed);
              ref.read(itemsProvider.notifier).showCompleted(_completed);
            },
          ),
          IconButton(
            tooltip: 'Sign out',
            icon: const Icon(Icons.logout),
            onPressed: () => ref.read(sessionProvider.notifier).signOut(),
          ),
        ],
      ),
      body: items.when(
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
    );
  }

  Widget _body(List<Item> all) {
    final filtered = applyChipFilter(all, child: _child, type: _type);
    final sections = groupItems(filtered, DateTime.now());
    final children = childValues(all);
    final types = typeValues(all);

    return CustomScrollView(
      slivers: [
        if (children.isNotEmpty || types.isNotEmpty)
          SliverToBoxAdapter(child: _chips(children, types)),
        if (sections.isEmpty)
          const SliverFillRemaining(
            hasScrollBody: false,
            child: Center(child: Text('No items yet.\nPull down to refresh.',
                textAlign: TextAlign.center)),
          ),
        for (final section in sections) ...[
          SliverToBoxAdapter(child: _header(section.title)),
          SliverList.separated(
            itemCount: section.items.length,
            separatorBuilder: (_, _) => const Divider(height: 1),
            itemBuilder: (context, i) => _ItemTile(item: section.items[i]),
          ),
        ],
      ],
    );
  }

  Widget _chips(List<String> children, List<String> types) => SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        child: Row(
          children: [
            FilterChip(
              label: const Text('All'),
              selected: _child == null && _type == null,
              onSelected: (_) => setState(() { _child = null; _type = null; }),
            ),
            for (final c in children) ...[
              const SizedBox(width: 6),
              FilterChip(
                label: Text(c),
                selected: _child == c,
                onSelected: (_) => setState(() { _child = c; _type = null; }),
              ),
            ],
            for (final t in types) ...[
              const SizedBox(width: 6),
              FilterChip(
                label: Text(t),
                selected: _type == t,
                onSelected: (_) => setState(() { _type = t; _child = null; }),
              ),
            ],
          ],
        ),
      );

  Widget _header(String title) => Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
        child: Text(title.toUpperCase(),
            style: const TextStyle(
                fontSize: 11, fontWeight: FontWeight.w700, letterSpacing: 0.5,
                color: Colors.grey)),
      );

  Future<void> _sync(BuildContext context) async {
    final messenger = ScaffoldMessenger.of(context);
    messenger.showSnackBar(const SnackBar(
      content: Text('Syncing inbox… (first sync can take a couple of minutes)'),
      duration: Duration(seconds: 8),
    ));
    try {
      final created = await ref.read(syncServiceProvider).runUntilDone();
      await ref.read(itemsProvider.notifier).refresh();
      messenger.hideCurrentSnackBar();
      messenger.showSnackBar(SnackBar(content: Text('Synced — $created new item(s)')));
    } on SyncFailedException catch (e) {
      messenger.hideCurrentSnackBar();
      messenger.showSnackBar(SnackBar(content: Text(e.message)));
    } catch (_) {
      messenger.hideCurrentSnackBar();
      messenger.showSnackBar(const SnackBar(content: Text('Sync failed. Try again.')));
    }
  }
}

class _ItemTile extends ConsumerWidget {
  const _ItemTile({required this.item});
  final Item item;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final done = item.status == 'done';
    final dismissed = item.status == 'dismissed';
    final closed = done || dismissed;

    final subtitleParts = <String>[
      if (item.date != null) [item.date, item.time].whereType<String>().join(' '),
      if (item.eventType != null) item.eventType!,
      if (item.childName != null) item.childName!,
    ].where((s) => s.isNotEmpty).toList();

    return ListTile(
      leading: Icon(item.isEvent ? Icons.event : Icons.check_circle_outline),
      title: Text(
        item.title,
        style: closed
            ? const TextStyle(decoration: TextDecoration.lineThrough, color: Colors.grey)
            : null,
      ),
      subtitle: subtitleParts.isEmpty ? null : Text(subtitleParts.join('  ·  ')),
      onTap: () => Navigator.of(context).push(
        MaterialPageRoute(builder: (_) => ItemDetailScreen(item: item)),
      ),
      trailing: closed
          ? Chip(label: Text(item.status))
          : PopupMenuButton<String>(
              onSelected: (status) =>
                  ref.read(itemsProvider.notifier).setStatus(item.id, status),
              itemBuilder: (context) => const [
                PopupMenuItem(value: 'done', child: Text('Mark done')),
                PopupMenuItem(value: 'dismissed', child: Text('Dismiss')),
              ],
            ),
    );
  }
}

class _Centered extends StatelessWidget {
  const _Centered({required this.message, required this.actionLabel, required this.onAction});
  final String message;
  final String actionLabel;
  final VoidCallback onAction;

  @override
  Widget build(BuildContext context) => Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(message),
            const SizedBox(height: 12),
            FilledButton(onPressed: onAction, child: Text(actionLabel)),
          ],
        ),
      );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && flutter test test/items/home_screen_test.dart`
Expected: PASS.

- [ ] **Step 5: Full suite + analyze + firewall guard**

Run: `cd frontend && flutter test && flutter analyze && cd .. && bash scripts/firewall-guard.sh`
Expected: all tests pass, analyze clean, firewall-guard exits 0.

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/ui/home_screen.dart frontend/test/items/home_screen_test.dart
git commit -m "feat(frontend): grouped filterable agenda home + item detail navigation

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Security audit + HANDOFF update

**Files:**
- Modify: `HANDOFF.md`

- [ ] **Step 1: Security audit (touches the items read path — data persistence)**

Dispatch `@security-auditor` on the branch diff: focus on the `status` filter (user isolation preserved — the `user_id` + `deleted_at` predicates still gate every query; no content reaches the ad layer; the detail screen shows only structured fields + the server-stamped Gmail link, no raw body). Address any BLOCK before proceeding.

- [ ] **Step 2: Update HANDOFF Track D row**

In `HANDOFF.md`, update the Track D row to note slice 1 shipped (grouped agenda + chips + detail + `status` filter) and that the calendar tab + settings/delete-account remain.

- [ ] **Step 3: Commit + push**

```bash
git add HANDOFF.md
git commit -m "docs: HANDOFF — Track D slice 1 (useful items view) shipped

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push
```

---

## Self-review notes

- **Spec coverage:** grouped agenda (Task 2+6), filter chips (Task 3+6), detail + open-email (Task 5), `status` filter + Show-completed (Task 1+4+6), firewall/privacy invariants (Task 7 audit). Non-goals (calendar, settings, push) intentionally absent.
- **Type consistency:** `groupItems`/`ItemSection`, `childValues`/`typeValues`/`applyChipFilter`, `ItemsService.list({status})`, `ItemsController.showCompleted`, `ItemDetailScreen({item, opener})`/`UrlOpener` are used with identical signatures across tasks.
- **Section titles** are the exact verbatim strings from Global Constraints in every task that renders or asserts them.
