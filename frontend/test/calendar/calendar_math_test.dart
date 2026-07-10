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
