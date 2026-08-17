import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/account/account_providers.dart';
import 'package:mamaflow/account/mailboxes.dart';
import 'package:mamaflow/account/paywall_screen.dart';
import 'package:mamaflow/account/purchases.dart';

/// The paywall (D47).
///
/// Prices and terms come from the STORE, never from constants in the app — a
/// hardcoded price is wrong in every other currency and wrong everywhere the
/// moment pricing changes. These pin that the screen renders what it was given.
///
/// The renewal disclosure is a COMPLIANCE requirement (California's ARL reaches
/// us as an out-of-province seller; Google requires it too), so it is asserted
/// like any other behaviour rather than treated as copy.

AccountPlan _plan({String tier = 'free'}) => AccountPlan(
      tier: tier,
      adsEnabled: tier == 'free',
      memberLimit: tier == 'family' ? 2 : 1,
      mailboxesConnected: 1,
      mailboxLimit: tier == 'family' ? 3 : (tier == 'pro' ? 2 : 1),
      canAddMailbox: tier != 'free',
    );

/// A PlanOffer without a real StoreKit Package — the paywall only reads the
/// display fields, and the platform channel is unregistered under flutter test.
PlanOffer _offer({
  required String tier,
  required String period,
  required String price,
  int trialDays = 0,
}) =>
    PlanOffer(
      package: null,
      tier: tier,
      period: period,
      price: price,
      trialDays: trialDays,
    );

Widget _screen({
  required List<PlanOffer> offers,
  AccountPlan? plan,
}) =>
    ProviderScope(
      overrides: [
        accountPlanProvider.overrideWith((ref) async => plan ?? _plan()),
        planOffersProvider.overrideWith((ref) async => offers),
      ],
      child: const MaterialApp(home: PaywallScreen()),
    );

void main() {
  testWidgets('shows the store price and term, not a hardcoded one',
      (tester) async {
    await tester.pumpWidget(_screen(offers: [
      _offer(tier: 'pro', period: 'monthly', price: r'$6.99'),
      _offer(tier: 'family', period: 'annual', price: r'$99.00'),
    ]));
    await tester.pumpAndSettle();

    expect(find.textContaining(r'$6.99 per month'), findsOneWidget);
    expect(find.textContaining(r'$99.00 per year'), findsOneWidget);
    expect(find.text('Pro · Monthly'), findsOneWidget);
    expect(find.text('Family · Yearly'), findsOneWidget);
  });

  testWidgets('a trial states its length and what happens after',
      (tester) async {
    await tester.pumpWidget(_screen(offers: [
      _offer(tier: 'pro', period: 'monthly', price: r'$6.99', trialDays: 7),
    ]));
    await tester.pumpAndSettle();

    expect(
      find.textContaining(r'7-day free trial, then $6.99 per month'),
      findsOneWidget,
    );
  });

  testWidgets('the auto-renewal disclosure is present', (tester) async {
    /// Required before purchase, not in a linked policy. Deleting this text is
    /// a compliance change, so it is pinned here.
    await tester.pumpWidget(_screen(offers: [
      _offer(tier: 'pro', period: 'monthly', price: r'$6.99', trialDays: 7),
    ]));
    await tester.pumpAndSettle();

    expect(find.textContaining('renew automatically'), findsOneWidget);
    expect(find.textContaining('converts to a paid plan'), findsOneWidget);
    expect(find.textContaining('cancel any time'), findsOneWidget);
    // And that cancelling doesn't cut them off early — the thing users most
    // often get wrong about subscriptions.
    expect(find.textContaining('keep access'), findsOneWidget);
  });

  testWidgets('offers restore, for a reinstall or a second device',
      (tester) async {
    await tester.pumpWidget(_screen(offers: [
      _offer(tier: 'pro', period: 'monthly', price: r'$6.99'),
    ]));
    await tester.pumpAndSettle();

    expect(find.text('Restore purchases'), findsOneWidget);
  });

  testWidgets('no offers explains rather than showing an empty screen',
      (tester) async {
    await tester.pumpWidget(_screen(offers: const []));
    await tester.pumpAndSettle();

    expect(find.textContaining("aren't available"), findsOneWidget);
  });

  testWidgets('an existing subscriber is told what they already have',
      (tester) async {
    await tester.pumpWidget(_screen(
      offers: [_offer(tier: 'family', period: 'monthly', price: r'$9.99')],
      plan: _plan(tier: 'pro'),
    ));
    await tester.pumpAndSettle();

    expect(find.textContaining("You're on Pro"), findsOneWidget);
  });

  testWidgets('a free user is not told they are on a plan', (tester) async {
    await tester.pumpWidget(_screen(
      offers: [_offer(tier: 'pro', period: 'monthly', price: r'$6.99')],
      plan: _plan(),
    ));
    await tester.pumpAndSettle();

    expect(find.textContaining("You're on"), findsNothing);
  });
}
