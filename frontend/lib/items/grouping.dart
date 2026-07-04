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
