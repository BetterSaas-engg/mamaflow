import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/account/account_providers.dart';
import 'package:mamaflow/account/mailboxes.dart';
import 'package:mamaflow/account/mailboxes_screen.dart';

/// The mailbox management screen (D44/D45).
///
/// The limits shown here must come from the server. If the app ever derives
/// them from the tier string instead, the number a user sees and the number
/// the backend enforces can disagree — so these pin that the screen renders
/// whatever the API said, including a plan it has never heard of.
AccountPlan _plan({
  String tier = 'free',
  int connected = 1,
  int limit = 1,
  bool canAdd = false,
}) =>
    AccountPlan(
      tier: tier,
      adsEnabled: tier == 'free',
      memberLimit: tier == 'family' ? 2 : 1,
      mailboxesConnected: connected,
      mailboxLimit: limit,
      canAddMailbox: canAdd,
    );

Widget _screen({
  required AccountPlan plan,
  required List<Mailbox> mailboxes,
}) =>
    ProviderScope(
      overrides: [
        accountPlanProvider.overrideWith((ref) async => plan),
        mailboxListProvider.overrideWith((ref) async => mailboxes),
      ],
      child: const MaterialApp(home: MailboxesScreen()),
    );

void main() {
  testWidgets('shows the plan and how many mailboxes are used', (tester) async {
    await tester.pumpWidget(_screen(
      plan: _plan(tier: 'pro', connected: 1, limit: 2, canAdd: true),
      mailboxes: const [
        Mailbox(id: '1', provider: 'google', email: 'mum@gmail.com'),
      ],
    ));
    await tester.pumpAndSettle();

    expect(find.text('Pro plan'), findsOneWidget);
    expect(find.text('1 of 2 email accounts connected'), findsOneWidget);
    expect(find.text('mum@gmail.com'), findsOneWidget);
    expect(find.text('Gmail'), findsOneWidget);
  });

  testWidgets('offers to add another when the plan allows it', (tester) async {
    await tester.pumpWidget(_screen(
      plan: _plan(tier: 'pro', connected: 1, limit: 2, canAdd: true),
      mailboxes: const [
        Mailbox(id: '1', provider: 'yahoo', email: 'mum@yahoo.com'),
      ],
    ));
    await tester.pumpAndSettle();

    final tile = tester.widget<ListTile>(
      find.ancestor(
        of: find.text('Add another email'),
        matching: find.byType(ListTile),
      ),
    );
    expect(tile.enabled, isTrue);
  });

  testWidgets('at the limit, explains the limit instead of dead-ending',
      (tester) async {
    await tester.pumpWidget(_screen(
      plan: _plan(connected: 1, limit: 1, canAdd: false),
      mailboxes: const [
        Mailbox(id: '1', provider: 'google', email: 'mum@gmail.com'),
      ],
    ));
    await tester.pumpAndSettle();

    // Says what the plan includes AND what the user can do about it — there
    // is no purchase flow yet, so "upgrade" alone would be a dead end.
    expect(find.textContaining('Free plan includes 1 email account'),
        findsOneWidget);
    expect(find.textContaining('Disconnect one'), findsOneWidget);
  });

  testWidgets('an empty state says why nothing is being scanned',
      (tester) async {
    await tester.pumpWidget(_screen(
      plan: _plan(connected: 0, limit: 1, canAdd: true),
      mailboxes: const [],
    ));
    await tester.pumpAndSettle();

    expect(find.textContaining('No email connected'), findsOneWidget);
  });

  testWidgets('disconnect asks first and says what it will do', (tester) async {
    await tester.pumpWidget(_screen(
      plan: _plan(),
      mailboxes: const [
        Mailbox(id: '1', provider: 'yahoo', email: 'mum@yahoo.com'),
      ],
    ));
    await tester.pumpAndSettle();

    await tester.tap(find.byIcon(Icons.link_off));
    await tester.pumpAndSettle();

    expect(find.text('Disconnect this email?'), findsOneWidget);
    // The credential consequence is the non-obvious part, so it must be said.
    expect(find.textContaining('delete the password'), findsOneWidget);
    expect(find.textContaining('stay in your calendar'), findsOneWidget);
  });

  testWidgets('renders a tier the app has never heard of without breaking',
      (tester) async {
    // The server resolves entitlements; a newer plan name must not blank the
    // screen or hide the user's mailboxes.
    await tester.pumpWidget(_screen(
      plan: _plan(tier: 'founders', connected: 3, limit: 5, canAdd: true),
      mailboxes: const [
        Mailbox(id: '1', provider: 'weirdmail', email: 'x@y.com'),
      ],
    ));
    await tester.pumpAndSettle();

    expect(find.text('3 of 5 email accounts connected'), findsOneWidget);
    expect(find.text('weirdmail'), findsOneWidget);  // falls back to the key
  });
}
