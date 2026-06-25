import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/items/item.dart';
import 'package:mamaflow/items/items_controller.dart';
import 'package:mamaflow/items/items_service.dart';
import 'package:mamaflow/ui/home_screen.dart';
import 'package:mocktail/mocktail.dart';

class _MockItemsService extends Mock implements ItemsService {}

Widget _host(ItemsService svc) => ProviderScope(
      overrides: [itemsServiceProvider.overrideWithValue(svc)],
      child: const MaterialApp(home: HomeScreen()),
    );

void main() {
  testWidgets('renders items returned by the service', (tester) async {
    final svc = _MockItemsService();
    when(() => svc.list()).thenAnswer((_) async => const [
          Item(
            id: 'i1',
            itemType: 'event',
            status: 'open',
            eventTitle: 'Soccer practice',
            date: '2026-06-20',
            eventType: 'sports',
          ),
        ]);

    await tester.pumpWidget(_host(svc));
    await tester.pumpAndSettle();

    expect(find.text('Soccer practice'), findsOneWidget);
    expect(find.textContaining('sports'), findsOneWidget);
  });

  testWidgets('shows empty state when there are no items', (tester) async {
    final svc = _MockItemsService();
    when(() => svc.list()).thenAnswer((_) async => const <Item>[]);

    await tester.pumpWidget(_host(svc));
    await tester.pumpAndSettle();

    expect(find.textContaining('No items yet'), findsOneWidget);
  });
}
