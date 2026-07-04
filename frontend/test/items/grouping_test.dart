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
