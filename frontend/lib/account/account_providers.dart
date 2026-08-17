import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../auth/session_controller.dart';
import '../core/providers.dart';
import 'account_service.dart';
import 'jwt_email.dart';
import 'household.dart';
import 'mailboxes.dart';
import 'purchases.dart';

/// The signed-in account's email, read from the stored session JWT. Null if
/// no token or no email claim.
final accountEmailProvider = FutureProvider<String?>((ref) async {
  // Recompute when auth state flips (sign-out / sign-in as a different
  // account) so a stale email from a prior session can't linger.
  ref.watch(sessionProvider);
  final jwt = await ref.watch(tokenStoreProvider).readJwt();
  return emailFromJwt(jwt);
});

final accountServiceProvider =
    Provider<AccountService>((ref) => AccountService(ref.watch(apiClientProvider)));

/// Mailbox management (D44/D45).
final mailboxServiceProvider =
    Provider<MailboxService>((ref) => MailboxService(ref.watch(apiClientProvider)));

/// The account's plan + limits, computed server-side. Recomputed when auth
/// flips so a previous account's plan can't linger.
final accountPlanProvider = FutureProvider<AccountPlan>((ref) {
  ref.watch(sessionProvider);
  return ref.watch(mailboxServiceProvider).plan();
});

final mailboxListProvider = FutureProvider<List<Mailbox>>((ref) {
  ref.watch(sessionProvider);
  return ref.watch(mailboxServiceProvider).list();
});

/// Family sharing (D46).
final householdServiceProvider = Provider<HouseholdService>(
    (ref) => HouseholdService(ref.watch(apiClientProvider)));

final householdProvider = FutureProvider<HouseholdView>((ref) {
  ref.watch(sessionProvider);
  return ref.watch(householdServiceProvider).get();
});

/// Billing (D47).
final purchasesServiceProvider = Provider<PurchasesService>(
  (ref) => PurchasesService(ref.watch(apiClientProvider)),
);

/// What the store is offering. Empty (not an error) when billing isn't
/// configured for this build, so the paywall degrades to an explanation.
final planOffersProvider = FutureProvider<List<PlanOffer>>((ref) {
  ref.watch(sessionProvider);
  return ref.watch(purchasesServiceProvider).offers();
});

/// Ads are the free tier's price (D21) — a paid plan removes them, and the
/// SERVER decides which you are on.
///
/// Defaults to **false while loading**, so an ad slot never flashes in for
/// someone who has paid. `kShowAds` still gates the build entirely, so this
/// can only ever turn ads off, never on.
final serverAdsEnabledProvider = Provider<bool>((ref) {
  if (!kShowAds) return false;
  return ref.watch(accountPlanProvider).maybeWhen(
        data: (plan) => plan.adsEnabled,
        orElse: () => false,
      );
});
