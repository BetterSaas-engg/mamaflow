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
}
