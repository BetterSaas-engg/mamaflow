import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/app.dart';
import 'package:mamaflow/auth/auth_service.dart';
import 'package:mamaflow/core/providers.dart';
import 'package:mocktail/mocktail.dart';

class _MockAuth extends Mock implements AuthService {}

Widget _app(AuthService auth) => ProviderScope(
      overrides: [authServiceProvider.overrideWithValue(auth)],
      child: const MamaflowApp(),
    );

void main() {
  testWidgets('auth gate shows sign-in when there is no session', (tester) async {
    final auth = _MockAuth();
    when(() => auth.isSignedIn()).thenAnswer((_) async => false);

    await tester.pumpWidget(_app(auth));
    await tester.pumpAndSettle();

    expect(find.text('Continue with Google'), findsOneWidget);
  });

  testWidgets('auth gate shows home when a session is present', (tester) async {
    final auth = _MockAuth();
    when(() => auth.isSignedIn()).thenAnswer((_) async => true);

    await tester.pumpWidget(_app(auth));
    await tester.pumpAndSettle();

    expect(find.text('Mamaflow'), findsWidgets);
    expect(find.byTooltip('Sign out'), findsOneWidget);
  });
}
