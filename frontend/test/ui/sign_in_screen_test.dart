import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/theme/app_logo.dart';
import 'package:mamaflow/ui/sign_in_screen.dart';

void main() {
  testWidgets('renders the brand, tagline, trust lines and CTA', (tester) async {
    await tester.pumpWidget(const ProviderScope(
      child: MaterialApp(home: SignInScreen()),
    ));
    await tester.pumpAndSettle();

    expect(find.byType(AppLogo), findsOneWidget);
    expect(find.text('Mamaflow'), findsOneWidget);
    expect(find.text('Your family calendar, from your inbox.'), findsOneWidget);
    expect(find.textContaining('never used for ads'), findsOneWidget);
    // NB: use find.text, not widgetWithText(FilledButton, …) — FilledButton.icon
    // has a private runtime type that find.byType(FilledButton) won't match.
    expect(find.text('Continue with Google'), findsOneWidget);
  });

  testWidgets('Google sign-in is gated behind the disclosure', (tester) async {
    // The requirement is that the disclosure IMMEDIATELY precedes the consent
    // request. If the button ever calls signIn() directly again, this fails —
    // and nothing else would notice until Google refused verification.
    await tester.pumpWidget(const ProviderScope(
      child: MaterialApp(home: SignInScreen()),
    ));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Continue with Google'));
    await tester.pumpAndSettle();

    expect(find.text('Before you connect Gmail'), findsOneWidget);
    expect(find.textContaining('Limited Use requirements'), findsOneWidget);
  });

  testWidgets('declining the disclosure is not an error state', (tester) async {
    await tester.pumpWidget(const ProviderScope(
      child: MaterialApp(home: SignInScreen()),
    ));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Continue with Google'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Not now'));
    await tester.pumpAndSettle();

    // Backing out is a normal choice — no scary red text, nothing to retry.
    expect(find.textContaining('Sign-in failed'), findsNothing);
    expect(find.text('Continue with Google'), findsOneWidget);
  });
}
