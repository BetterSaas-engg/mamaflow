import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/account/account_providers.dart';
import 'package:mamaflow/account/account_service.dart';
import 'package:mamaflow/ui/settings_screen.dart';
import 'package:mocktail/mocktail.dart';

class _MockAccount extends Mock implements AccountService {}

Widget _host(AccountService account) => ProviderScope(
      overrides: [
        accountServiceProvider.overrideWithValue(account),
        accountEmailProvider.overrideWith((ref) async => 'parent@example.com'),
      ],
      child: const MaterialApp(home: SettingsScreen()),
    );

void main() {
  testWidgets('shows the account email', (tester) async {
    await tester.pumpWidget(_host(_MockAccount()));
    await tester.pumpAndSettle();
    expect(find.text('parent@example.com'), findsOneWidget);
  });

  testWidgets('delete button is gated on typing DELETE, then calls the service',
      (tester) async {
    final account = _MockAccount();
    when(() => account.deleteAccount()).thenAnswer((_) async {});

    await tester.pumpWidget(_host(account));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Delete account'));
    await tester.pumpAndSettle();

    // The confirm button exists but is disabled until "DELETE" is typed.
    final confirm = find.widgetWithText(FilledButton, 'Delete account');
    expect(tester.widget<FilledButton>(confirm).onPressed, isNull);

    await tester.enterText(find.byType(TextField), 'DELETE');
    await tester.pump();
    expect(tester.widget<FilledButton>(confirm).onPressed, isNotNull);

    await tester.tap(confirm);
    await tester.pumpAndSettle();

    verify(() => account.deleteAccount()).called(1);
  });
}
