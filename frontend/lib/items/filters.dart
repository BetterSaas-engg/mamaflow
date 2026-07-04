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
