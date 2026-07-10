import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/items/item.dart';
import 'package:mamaflow/items/items_controller.dart';
import 'package:mamaflow/items/items_service.dart';
import 'package:mocktail/mocktail.dart';

class _MockService extends Mock implements ItemsService {}

Item _item(String id, {required String status}) =>
    Item(id: id, itemType: 'event', status: status, eventTitle: id, date: '2026-07-05');

void main() {
  test('calendar loads OPEN items regardless of the Agenda completed toggle', () async {
    final svc = _MockService();
    when(() => svc.list(status: 'open')).thenAnswer((_) async => [_item('open', status: 'open')]);
    when(() => svc.list(status: 'done')).thenAnswer((_) async => [_item('done', status: 'done')]);

    final container = ProviderContainer(overrides: [itemsServiceProvider.overrideWithValue(svc)]);
    addTearDown(container.dispose);

    // Agenda toggles to completed -> itemsProvider now holds done items.
    await container.read(itemsProvider.future);
    await container.read(itemsProvider.notifier).showCompleted(true);

    // Calendar still shows open items — it uses its own provider.
    final cal = await container.read(calendarItemsProvider.future);
    expect(cal.map((i) => i.id), ['open']);
  });
}
