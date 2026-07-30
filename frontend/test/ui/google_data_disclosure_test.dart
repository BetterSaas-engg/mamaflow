import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/ui/google_data_disclosure.dart';

/// The in-app disclosure Google requires before a restricted-scope consent
/// request. Each of these pins a specific verification requirement — a missing
/// or weakened disclosure is a documented rejection, and the failure is silent
/// (the app works fine; verification just gets refused weeks later).
/// See docs/e0-oauth-verification.md.
void main() {
  Future<bool?> pumpAndOpen(WidgetTester tester) async {
    bool? result;
    await tester.pumpWidget(MaterialApp(
      home: Builder(
        builder: (context) => Scaffold(
          body: ElevatedButton(
            onPressed: () async {
              result = await showGoogleDataDisclosure(context);
            },
            child: const Text('open'),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    return result;
  }

  testWidgets('states what is read, how it is used, and who it is shared with',
      (tester) async {
    await pumpAndOpen(tester);

    // The policy is explicit that this substance "cannot be placed only in a
    // privacy policy" — it has to be on this screen.
    expect(find.textContaining('read-only'), findsOneWidget);
    expect(find.textContaining('events'), findsWidgets);
    expect(find.textContaining('Anthropic'), findsOneWidget);
  });

  testWidgets('carries the Limited Use adherence statement', (tester) async {
    await pumpAndOpen(tester);

    expect(find.textContaining('Limited Use requirements'), findsOneWidget);
    expect(
      find.textContaining('Google API Services User Data Policy'),
      findsOneWidget,
    );
  });

  testWidgets('agreeing requires an affirmative tap', (tester) async {
    bool? result;
    await tester.pumpWidget(MaterialApp(
      home: Builder(
        builder: (context) => Scaffold(
          body: ElevatedButton(
            onPressed: () async {
              result = await showGoogleDataDisclosure(context);
            },
            child: const Text('open'),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('I agree, continue'));
    await tester.pumpAndSettle();

    expect(result, isTrue);
  });

  testWidgets('declining returns false', (tester) async {
    bool? result;
    await tester.pumpWidget(MaterialApp(
      home: Builder(
        builder: (context) => Scaffold(
          body: ElevatedButton(
            onPressed: () async {
              result = await showGoogleDataDisclosure(context);
            },
            child: const Text('open'),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Not now'));
    await tester.pumpAndSettle();

    expect(result, isFalse);
  });

  testWidgets('tapping outside does not count as consent', (tester) async {
    bool? result;
    var completed = false;
    await tester.pumpWidget(MaterialApp(
      home: Builder(
        builder: (context) => Scaffold(
          body: ElevatedButton(
            onPressed: () async {
              result = await showGoogleDataDisclosure(context);
              completed = true;
            },
            child: const Text('open'),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();

    // Barrier tap: the policy says navigating away must never be treated as
    // consent, so this must not dismiss into a `true`.
    await tester.tapAt(const Offset(10, 10));
    await tester.pumpAndSettle();

    expect(completed, isFalse, reason: 'the dialog dismissed on a barrier tap');
    expect(result, isNull);
    expect(find.text('I agree, continue'), findsOneWidget);
  });
}
