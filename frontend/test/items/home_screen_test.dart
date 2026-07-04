import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
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
