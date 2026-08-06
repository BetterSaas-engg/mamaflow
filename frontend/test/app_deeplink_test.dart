import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mamaflow/ui/sign_in_screen.dart';

/// The OAuth callback arrives as a deep link, and Flutter hands deep links to
/// the router as a location to open. It is a credential delivery, not a page —
/// so the router must not 404 on it.
///
/// Reported from a real device: after completing Google consent the app showed
/// "Page Not Found — GoException: no routes for location:
/// com.googleusercontent.apps.<id>:/oauth2redirect?code=…" on top of a sign-in
/// that had actually succeeded.
void main() {
  Widget appWith(String initialLocation) {
    final router = GoRouter(
      initialLocation: initialLocation,
      routes: [
        GoRoute(path: '/', builder: (_, _) => const SignInScreen()),
      ],
      onException: (context, state, router) => router.go('/'),
    );
    return ProviderScope(
      child: MaterialApp.router(routerConfig: router),
    );
  }

  testWidgets('the OAuth callback does not render a 404', (tester) async {
    await tester.pumpWidget(appWith(
      'com.googleusercontent.apps.682580051335-abc:/oauth2redirect'
      '?state=xyz&code=4/0AXEQ',
    ));
    await tester.pumpAndSettle();

    expect(find.textContaining('Page Not Found'), findsNothing);
    expect(find.textContaining('GoException'), findsNothing);
    // Lands on the gate instead, which shows the right screen for the session.
    expect(find.text('Continue with Google'), findsOneWidget);
  });

  testWidgets('any other unroutable deep link also lands on the gate',
      (tester) async {
    await tester.pumpWidget(appWith('/nonsense/path'));
    await tester.pumpAndSettle();

    expect(find.textContaining('Page Not Found'), findsNothing);
    expect(find.text('Continue with Google'), findsOneWidget);
  });

  testWidgets('a normal launch still works', (tester) async {
    await tester.pumpWidget(appWith('/'));
    await tester.pumpAndSettle();

    expect(find.text('Continue with Google'), findsOneWidget);
  });
}
