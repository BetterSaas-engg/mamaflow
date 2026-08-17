import 'package:flutter/foundation.dart';
import 'package:purchases_flutter/purchases_flutter.dart';

import '../core/api_client.dart';

/// One thing the user can buy.
class PlanOffer {
  const PlanOffer({
    required this.package,
    required this.tier,
    required this.period,
    required this.price,
    this.trialDays = 0,
  });

  /// The store package to buy. Null when an offer has no store package behind
  /// it — today that means a test fixture, and later a web/Stripe offer, which
  /// the stores' rules already require us to keep separate from IAP.
  final Package? package;
  final String tier;      // 'pro' | 'family'
  final String period;    // 'monthly' | 'annual'
  final String price;     // already localised by the store
  final int trialDays;

  String get tierLabel => tier == 'family' ? 'Family' : 'Pro';
  String get periodLabel => period == 'annual' ? 'year' : 'month';
}

/// Buying a plan, and telling the backend about it.
///
/// The **server** decides entitlements — this class never grants anything. It
/// starts the purchase, then asks the backend to reconcile, and the backend's
/// `/account/me` remains the only source of truth for what the user gets. That
/// separation is why a cracked client cannot hand itself Family: the store
/// tells RevenueCat, RevenueCat tells our webhook, and only then does the tier
/// move.
class PurchasesService {
  PurchasesService(this._api, {PurchasesPlatform? platform})
      : _platform = platform ?? const _RealPurchases();

  final ApiClient _api;
  final PurchasesPlatform _platform;

  /// Bind purchases to our account id, so a webhook can find the user.
  /// `users.id` is opaque, non-PII, and already the JWT subject — RevenueCat's
  /// own guidance is to use an id like this rather than anything derived from
  /// an email address.
  Future<void> identify(String userId) => _platform.logIn(userId);

  Future<void> forget() => _platform.logOut();

  Future<List<PlanOffer>> offers() async {
    final offerings = await _platform.getOfferings();
    final current = offerings.current;
    if (current == null) return const [];
    final result = <PlanOffer>[];
    for (final package in current.availablePackages) {
      final product = package.storeProduct;
      final id = '${package.identifier} ${product.identifier}'.toLowerCase();
      // Tier and term are read from the identifiers rather than a hardcoded
      // SKU table, so adding a product in the store doesn't need an app
      // release. Same reasoning as the backend's tier_for_product.
      final tier = id.contains('family') ? 'family' : 'pro';
      final period = id.contains('annual') || id.contains('year')
          ? 'annual'
          : 'monthly';
      result.add(PlanOffer(
        package: package,
        tier: tier,
        period: period,
        price: product.priceString,
        trialDays: _trialDays(product),
      ));
    }
    // Cheapest-looking first (monthly), and Pro before Family.
    result.sort((a, b) {
      final byTier = (a.tier == 'family' ? 1 : 0) - (b.tier == 'family' ? 1 : 0);
      if (byTier != 0) return byTier;
      return (a.period == 'annual' ? 1 : 0) - (b.period == 'annual' ? 1 : 0);
    });
    return result;
  }

  static int _trialDays(StoreProduct product) {
    final period = product.introductoryPrice?.period;
    if (period == null) return 0;
    final match = RegExp(r'(\d+)').firstMatch(period);
    final n = match == null ? 0 : int.tryParse(match.group(1)!) ?? 0;
    if (period.toUpperCase().contains('W')) return n * 7;
    if (period.toUpperCase().contains('M')) return n * 30;
    return n;
  }

  /// Buy a plan, then have the server reconcile.
  ///
  /// Returns the app user id the purchase was made under. The backend is asked
  /// to link it even on a purchase that looks successful, because the webhook
  /// may not have arrived yet — and linking is idempotent.
  Future<String> purchase(PlanOffer offer) async {
    final package = offer.package;
    if (package == null) {
      throw StateError('This plan cannot be bought through the app store.');
    }
    await _platform.purchasePackage(package);
    final appUserId = await _platform.appUserId();
    await _syncWithBackend(appUserId);
    return appUserId;
  }

  /// "Restore purchases" — and the routine reconciliation path.
  ///
  /// Worth calling on cold start after login: it is what claims a purchase
  /// made on the paywall *before* signing in, which arrives under an anonymous
  /// RevenueCat id with no user attached.
  Future<void> restore() async {
    await _platform.restorePurchases();
    await _syncWithBackend(await _platform.appUserId());
  }

  Future<void> _syncWithBackend(String appUserId) =>
      _api.postJson('/api/v1/account/billing/link', {'app_user_id': appUserId});
}

/// Seam over the RevenueCat SDK. Its platform channel is unregistered under
/// `flutter test`, so the service is only testable through an interface —
/// same pattern as the ad slot's `bannerBuilder`.
abstract class PurchasesPlatform {
  Future<void> logIn(String userId);
  Future<void> logOut();
  Future<Offerings> getOfferings();
  Future<void> purchasePackage(Package package);
  Future<void> restorePurchases();
  Future<String> appUserId();
}

class _RealPurchases implements PurchasesPlatform {
  const _RealPurchases();

  @override
  Future<void> logIn(String userId) => Purchases.logIn(userId);

  @override
  Future<void> logOut() => Purchases.logOut();

  @override
  Future<Offerings> getOfferings() => Purchases.getOfferings();

  @override
  Future<void> purchasePackage(Package package) =>
      Purchases.purchase(PurchaseParams.package(package));

  @override
  Future<void> restorePurchases() => Purchases.restorePurchases();

  @override
  Future<String> appUserId() => Purchases.appUserID;
}

/// Configure the SDK. Inert without a key, so a build without billing
/// configured simply has no paywall rather than crashing at startup.
const kRevenueCatApiKey = String.fromEnvironment('REVENUECAT_API_KEY');

Future<void> initPurchases() async {
  if (kRevenueCatApiKey.isEmpty) return;
  try {
    await Purchases.configure(PurchasesConfiguration(kRevenueCatApiKey));
  } catch (e) {
    // Billing being unavailable must never stop the app starting — the
    // calendar is the product, the paywall is not.
    debugPrint('purchases: configure failed (${e.runtimeType})');
  }
}
