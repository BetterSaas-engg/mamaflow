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
