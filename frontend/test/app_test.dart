import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/app.dart';
import 'package:mamaflow/auth/auth_service.dart';
import 'package:mamaflow/core/providers.dart';
import 'package:mamaflow/items/item.dart';
import 'package:mamaflow/items/items_controller.dart';
import 'package:mamaflow/items/items_service.dart';
import 'package:mocktail/mocktail.dart';

class _MockAuth extends Mock implements AuthService {}

class _MockItemsService extends Mock implements ItemsService {}

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
    when(() => items.list()).thenAnswer((_) async => const <Item>[]);

    await tester.pumpWidget(ProviderScope(
      overrides: [
        authServiceProvider.overrideWithValue(auth),
        itemsServiceProvider.overrideWithValue(items),
      ],
      child: const MamaflowApp(),
    ));
    await tester.pumpAndSettle();

    expect(find.text('Mamaflow'), findsWidgets);
    expect(find.byTooltip('Settings'), findsOneWidget);
  });
}
