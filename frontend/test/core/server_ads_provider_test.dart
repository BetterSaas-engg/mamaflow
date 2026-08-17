import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/account/account_providers.dart';
import 'package:mamaflow/account/mailboxes.dart';

/// Ads are the free tier's price (D21) — paying removes them, and the SERVER
/// decides which tier you are on (D47).
AccountPlan _plan({required bool ads}) => AccountPlan(
      tier: ads ? 'free' : 'pro',
      adsEnabled: ads,
      memberLimit: 1,
      mailboxesConnected: 1,
      mailboxLimit: ads ? 1 : 2,
      canAddMailbox: !ads,
    );

void main() {
  test('a paid plan turns ads off', () async {
    final c = ProviderContainer(overrides: [
      accountPlanProvider.overrideWith((ref) async => _plan(ads: false)),
    ]);
    addTearDown(c.dispose);
    await c.read(accountPlanProvider.future);

    expect(c.read(serverAdsEnabledProvider), isFalse);
  });

  test('ads stay off while the plan is still loading', () async {
    /// The slot must never flash in for someone who has paid, so the default
    /// during load is OFF rather than on.
    final c = ProviderContainer(overrides: [
      accountPlanProvider.overrideWith(
        (ref) => Future.delayed(const Duration(seconds: 1), () => _plan(ads: true)),
      ),
    ]);
    addTearDown(c.dispose);

    expect(c.read(serverAdsEnabledProvider), isFalse);
  });

  test('the build flag still wins — this can only turn ads off, never on',
      () async {
    /// kShowAds is false in tests, so even a free plan must not enable ads.
    /// Otherwise a server response could switch on an SDK the build never
    /// initialised.
    final c = ProviderContainer(overrides: [
      accountPlanProvider.overrideWith((ref) async => _plan(ads: true)),
    ]);
    addTearDown(c.dispose);
    await c.read(accountPlanProvider.future);

    expect(c.read(serverAdsEnabledProvider), isFalse);
  });
}
