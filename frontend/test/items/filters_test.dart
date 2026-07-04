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
