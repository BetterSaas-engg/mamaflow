import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/items/item.dart';
import 'package:mamaflow/items/items_controller.dart';
import 'package:mamaflow/items/items_service.dart';
import 'package:mamaflow/ui/calendar_screen.dart';
import 'package:mocktail/mocktail.dart';

class _MockService extends Mock implements ItemsService {}

Item _item(String id, {required String date}) =>
    Item(id: id, itemType: 'event', status: 'open', eventTitle: id, date: date);

Widget _host(ItemsService svc) => ProviderScope(
      overrides: [itemsServiceProvider.overrideWithValue(svc)],
      child: const MaterialApp(home: CalendarScreen()),
    );

void main() {
  setUpAll(() => registerFallbackValue('open'));

  testWidgets('shows the current month and lists a tapped day\'s items',
      (tester) async {
    final now = DateTime.now();
    final iso =
        '${now.year.toString().padLeft(4, '0')}-${now.month.toString().padLeft(2, '0')}-${now.day.toString().padLeft(2, '0')}';
    final svc = _MockService();
    when(() => svc.list(status: any(named: 'status')))
        .thenAnswer((_) async => [_item('Soccer', date: iso)]);

    await tester.pumpWidget(_host(svc));
    await tester.pumpAndSettle();

    // Tap today's cell (day number is rendered as text).
    await tester.tap(find.text('${now.day}').first);
    await tester.pumpAndSettle();

    expect(find.text('Soccer'), findsOneWidget);
  });
}
