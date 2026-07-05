import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/items/item.dart';
import 'package:mamaflow/items/items_controller.dart';
import 'package:mamaflow/items/items_service.dart';
import 'package:mamaflow/ui/home_shell.dart';
import 'package:mocktail/mocktail.dart';

class _MockService extends Mock implements ItemsService {}

void main() {
  setUpAll(() => registerFallbackValue('open'));

  testWidgets('has Agenda + Calendar tabs and switches to the calendar',
      (tester) async {
    final svc = _MockService();
    when(() => svc.list(status: any(named: 'status')))
        .thenAnswer((_) async => <Item>[]);

    await tester.pumpWidget(ProviderScope(
      overrides: [itemsServiceProvider.overrideWithValue(svc)],
      child: const MaterialApp(home: HomeShell()),
    ));
    await tester.pumpAndSettle();

    expect(find.text('Agenda'), findsOneWidget);
    expect(find.text('Calendar'), findsWidgets);

    await tester.tap(find.text('Calendar').last);
    await tester.pumpAndSettle();

    // The calendar app bar shows the current month/year title.
    final now = DateTime.now();
    const months = ['January','February','March','April','May','June','July','August','September','October','November','December'];
    expect(find.text('${months[now.month - 1]} ${now.year}'), findsOneWidget);
  });
}
