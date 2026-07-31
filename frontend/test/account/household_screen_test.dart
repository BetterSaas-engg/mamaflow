import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/account/account_providers.dart';
import 'package:mamaflow/account/household.dart';
import 'package:mamaflow/account/household_screen.dart';

/// Family sharing (D46).
///
/// The screen's job is to make the privacy trade clear BEFORE someone joins:
/// events are shared, inbox and password are not. Since the extractor captures
/// every appointment — work ones included — that isn't obvious, so these tests
/// pin the wording as a product guarantee, not decoration.
HouseholdView _view({
  bool exists = false,
  bool isOwner = false,
  int memberLimit = 2,
  List<HouseholdMember> members = const [],
}) =>
    HouseholdView(
      exists: exists,
      isOwner: isOwner,
      memberLimit: memberLimit,
      members: members,
      pendingInvites: 0,
    );

Widget _screen(HouseholdView view) => ProviderScope(
      overrides: [householdProvider.overrideWith((ref) async => view)],
      child: const MaterialApp(home: HouseholdScreen()),
    );

void main() {
  testWidgets('states what is shared and what is not', (tester) async {
    await tester.pumpWidget(_screen(_view()));
    await tester.pumpAndSettle();

    expect(find.textContaining('Only the events we find are shared'),
        findsOneWidget);
    expect(find.textContaining('never your inbox'), findsOneWidget);
  });

  testWidgets('a plan without sharing says so instead of offering it',
      (tester) async {
    await tester.pumpWidget(_screen(_view(memberLimit: 1)));
    await tester.pumpAndSettle();

    expect(find.textContaining('part of the Family plan'), findsOneWidget);
    expect(find.text('Invite my partner'), findsNothing);
  });

  testWidgets('a Family plan can invite', (tester) async {
    await tester.pumpWidget(_screen(_view(memberLimit: 2)));
    await tester.pumpAndSettle();

    expect(find.text('Invite my partner'), findsOneWidget);
    expect(find.text('I have a code'), findsOneWidget);
  });

  testWidgets('joining spells out the exposure before you type a code',
      (tester) async {
    await tester.pumpWidget(_screen(_view(memberLimit: 2)));
    await tester.pumpAndSettle();

    await tester.tap(find.text('I have a code'));
    await tester.pumpAndSettle();

    // Consent has to be informed: say what the other person will see.
    expect(
      find.textContaining('shares the events found in your email'),
      findsOneWidget,
    );
    expect(find.textContaining('inbox and password stay'), findsOneWidget);
  });

  testWidgets('lists members and marks the plan owner', (tester) async {
    await tester.pumpWidget(_screen(_view(
      exists: true,
      isOwner: true,
      members: const [
        HouseholdMember(id: '1', email: 'mum@example.com', isOwner: true),
        HouseholdMember(id: '2', email: 'dad@example.com', isOwner: false),
      ],
    )));
    await tester.pumpAndSettle();

    expect(find.text('mum@example.com'), findsOneWidget);
    expect(find.text('Plan owner'), findsOneWidget);
    expect(find.text('dad@example.com'), findsOneWidget);
    expect(find.text('Member'), findsOneWidget);
  });

  testWidgets('the owner cannot be removed from the list', (tester) async {
    await tester.pumpWidget(_screen(_view(
      exists: true,
      isOwner: true,
      members: const [
        HouseholdMember(id: '1', email: 'mum@example.com', isOwner: true),
        HouseholdMember(id: '2', email: 'dad@example.com', isOwner: false),
      ],
    )));
    await tester.pumpAndSettle();

    // Exactly one remove control: the member's. Removing the owner would
    // strand the plan, and the backend refuses it too.
    expect(find.byIcon(Icons.person_remove_outlined), findsOneWidget);
  });

  testWidgets('removing says what stops and that nothing is deleted',
      (tester) async {
    await tester.pumpWidget(_screen(_view(
      exists: true,
      isOwner: true,
      members: const [
        HouseholdMember(id: '1', email: 'mum@example.com', isOwner: true),
        HouseholdMember(id: '2', email: 'dad@example.com', isOwner: false),
      ],
    )));
    await tester.pumpAndSettle();

    await tester.tap(find.byIcon(Icons.person_remove_outlined));
    await tester.pumpAndSettle();

    expect(find.text('Stop sharing?'), findsOneWidget);
    expect(find.textContaining('Nothing is deleted'), findsOneWidget);
  });
}
