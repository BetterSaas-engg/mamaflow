import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/app.dart';
import 'package:mamaflow/auth/auth_service.dart';
import 'package:mamaflow/core/providers.dart';
import 'package:mamaflow/items/item.dart';
import 'package:mamaflow/items/items_controller.dart';
import 'package:mamaflow/items/items_service.dart';
import 'package:mamaflow/push/push_service.dart';
import 'package:mocktail/mocktail.dart';

class _MockAuth extends Mock implements AuthService {}

class _MockItemsService extends Mock implements ItemsService {}

class _MockPush extends Mock implements PushService {}

void main() {
  testWidgets('auth gate shows sign-in when there is no session', (tester) async {
    final auth = _MockAuth();
    when(() => auth.isSignedIn()).thenAnswer((_) async => false);

    await tester.pumpWidget(ProviderScope(
      overrides: [authServiceProvider.overrideWithValue(auth)],
      child: const MamaflowApp(),
    ));
    await tester.pumpAndSettle();

    expect(find.text('Continue with Google'), findsOneWidget);
  });

  testWidgets('auth gate shows home when a session is present', (tester) async {
    final auth = _MockAuth();
    when(() => auth.isSignedIn()).thenAnswer((_) async => true);
    final items = _MockItemsService();
    // The controller passes status: — an argless stub would never match and
    // the items load would silently error under this test.
    when(() => items.list(status: any(named: 'status')))
        .thenAnswer((_) async => const <Item>[]);
    final push = _MockPush();
    when(() => push.start()).thenAnswer((_) async {});

    await tester.pumpWidget(ProviderScope(
      overrides: [
        authServiceProvider.overrideWithValue(auth),
        itemsServiceProvider.overrideWithValue(items),
        pushServiceProvider.overrideWithValue(push),
      ],
      child: const MamaflowApp(),
    ));
    await tester.pumpAndSettle();

    expect(find.text('Mamaflow'), findsWidgets);
    expect(find.byTooltip('Settings'), findsOneWidget);
  });

  testWidgets('signing out pops stacked routes down to the sign-in screen',
      (tester) async {
    final auth = _MockAuth();
    when(() => auth.isSignedIn()).thenAnswer((_) async => true);
    when(() => auth.signOut()).thenAnswer((_) async {});
    final items = _MockItemsService();
    when(() => items.list(status: any(named: 'status')))
        .thenAnswer((_) async => const <Item>[]);
    final push = _MockPush();
    when(() => push.start()).thenAnswer((_) async {});
    when(() => push.stop()).thenAnswer((_) async {});
    when(() => push.stop(unregisterFromBackend: false))
        .thenAnswer((_) async {});

    await tester.pumpWidget(ProviderScope(
      overrides: [
        authServiceProvider.overrideWithValue(auth),
        itemsServiceProvider.overrideWithValue(items),
        pushServiceProvider.overrideWithValue(push),
      ],
      child: const MamaflowApp(),
    ));
    await tester.pumpAndSettle();

    // Stack Settings above the home shell, then sign out from it.
    await tester.tap(find.byTooltip('Settings'));
    await tester.pumpAndSettle();
    expect(find.text('Sign out'), findsOneWidget);

    await tester.tap(find.text('Sign out'));
    await tester.pumpAndSettle();

    // The stacked Settings screen must be gone — not left sitting (with
    // account details) above the sign-in screen.
    expect(find.text('Sign out'), findsNothing);
    expect(find.text('Continue with Google'), findsOneWidget);
  });
}
