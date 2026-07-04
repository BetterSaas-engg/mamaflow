import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
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
