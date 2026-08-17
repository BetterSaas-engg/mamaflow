import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/errors.dart';
import '../theme/tokens.dart';
import 'account_providers.dart';
import 'purchases.dart';

/// The upgrade screen.
///
/// Prices, terms and trial length all come from the STORE (via RevenueCat), not
/// from constants here — a hardcoded "$6.99" would be wrong in every other
/// currency, and wrong everywhere the moment pricing changes.
///
/// The renewal terms below are not decoration. A trial obliges us to state the
/// cost, the billing cycle and that it auto-renews *before* the purchase
/// (California's ARL, which reaches us as an out-of-province seller, and
/// Google's equivalent rule). Removing that text is a compliance change, not a
/// copy tweak.
class PaywallScreen extends ConsumerStatefulWidget {
  const PaywallScreen({super.key});

  @override
  ConsumerState<PaywallScreen> createState() => _PaywallScreenState();
}

class _PaywallScreenState extends ConsumerState<PaywallScreen> {
  bool _busy = false;
  String? _error;

  Future<void> _buy(PlanOffer offer) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref.read(purchasesServiceProvider).purchase(offer);
      // The SERVER decides what the user gets, so refresh everything that
      // depends on the tier rather than assuming the purchase granted it.
      ref.invalidate(accountPlanProvider);
      ref.invalidate(householdProvider);
      ref.invalidate(mailboxListProvider);
      if (mounted) Navigator.of(context).pop(true);
    } catch (e) {
      // A cancelled purchase is a deliberate act, not an error.
      if (isPurchaseCancelled(e)) {
        if (mounted) setState(() => _busy = false);
        return;
      }
      if (mounted) setState(() => _error = messageFor(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _restore() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    final messenger = ScaffoldMessenger.of(context);
    try {
      await ref.read(purchasesServiceProvider).restore();
      ref.invalidate(accountPlanProvider);
      ref.invalidate(householdProvider);
      messenger.showSnackBar(
        const SnackBar(content: Text('Purchases restored.')),
      );
    } catch (e) {
      if (mounted) setState(() => _error = messageFor(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final offers = ref.watch(planOffersProvider);
    final plan = ref.watch(accountPlanProvider);
    final text = Theme.of(context).textTheme;
    final scheme = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(title: const Text('Upgrade')),
      body: ListView(
        padding: const EdgeInsets.all(AppSpacing.lg),
        children: [
          Text('More inboxes, no ads', style: text.headlineSmall),
          const SizedBox(height: AppSpacing.sm),
          Text(
            'Mamaflow reads your email and turns it into your family calendar. '
            'A paid plan covers more inboxes and removes ads.',
            style: text.bodyMedium?.copyWith(color: scheme.onSurfaceVariant),
          ),
          const SizedBox(height: AppSpacing.lg),
          const _Benefit(
            icon: Icons.mark_email_read_outlined,
            title: 'Pro',
            body: 'Two inboxes — your personal and work email in one calendar.',
          ),
          const _Benefit(
            icon: Icons.family_restroom,
            title: 'Family',
            body: 'Three inboxes shared between two parents, one calendar, '
                'one bill.',
          ),
          const _Benefit(
            icon: Icons.block,
            title: 'No ads',
            body: 'On every plan above Free.',
          ),
          const SizedBox(height: AppSpacing.lg),
          plan.maybeWhen(
            data: (p) => p.tier == 'free'
                ? const SizedBox.shrink()
                : Padding(
                    padding: const EdgeInsets.only(bottom: AppSpacing.md),
                    child: Text(
                      "You're on ${p.tierLabel}.",
                      style: text.titleSmall,
                    ),
                  ),
            orElse: () => const SizedBox.shrink(),
          ),
          offers.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (_, _) => Text(
              "Plans aren't available right now. Try again in a moment.",
              style: text.bodyMedium?.copyWith(color: scheme.error),
            ),
            data: (list) => list.isEmpty
                ? Text(
                    "Plans aren't available on this device yet.",
                    style: text.bodyMedium?.copyWith(
                      color: scheme.onSurfaceVariant,
                    ),
                  )
                : Column(
                    children: [
                      for (final offer in list)
                        Padding(
                          padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                          child: _OfferTile(
                            offer: offer,
                            busy: _busy,
                            onTap: () => _buy(offer),
                          ),
                        ),
                    ],
                  ),
          ),
          if (_error != null) ...[
            const SizedBox(height: AppSpacing.md),
            Text(_error!, style: text.bodyMedium?.copyWith(color: scheme.error)),
          ],
          const SizedBox(height: AppSpacing.md),
          TextButton(
            onPressed: _busy ? null : _restore,
            child: const Text('Restore purchases'),
          ),
          const SizedBox(height: AppSpacing.md),
          // Required disclosure — see the class doc. Keep it above the fold of
          // the scroll, not buried in a linked policy.
          Text(
            'Plans renew automatically at the price shown until you cancel. '
            'Any free trial converts to a paid plan when it ends. Manage or '
            'cancel any time in your App Store or Google Play account '
            'settings — cancelling stops the next charge and you keep access '
            'until the period you have paid for runs out.',
            style: text.bodySmall?.copyWith(color: scheme.onSurfaceVariant),
          ),
        ],
      ),
    );
  }
}

class _OfferTile extends StatelessWidget {
  const _OfferTile({
    required this.offer,
    required this.busy,
    required this.onTap,
  });

  final PlanOffer offer;
  final bool busy;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final scheme = Theme.of(context).colorScheme;
    return OutlinedButton(
      onPressed: busy ? null : onTap,
      style: OutlinedButton.styleFrom(
        padding: const EdgeInsets.all(AppSpacing.md),
        alignment: Alignment.centerLeft,
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '${offer.tierLabel} · ${offer.period == "annual" ? "Yearly" : "Monthly"}',
                  style: text.titleSmall,
                ),
                if (offer.trialDays > 0)
                  Text(
                    '${offer.trialDays}-day free trial, then '
                    '${offer.price} per ${offer.periodLabel}',
                    style: text.bodySmall?.copyWith(
                      color: scheme.onSurfaceVariant,
                    ),
                  )
                else
                  Text(
                    '${offer.price} per ${offer.periodLabel}',
                    style: text.bodySmall?.copyWith(
                      color: scheme.onSurfaceVariant,
                    ),
                  ),
              ],
            ),
          ),
          const Icon(Icons.chevron_right),
        ],
      ),
    );
  }
}

class _Benefit extends StatelessWidget {
  const _Benefit({
    required this.icon,
    required this.title,
    required this.body,
  });

  final IconData icon;
  final String title;
  final String body;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.md),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 20, color: scheme.primary),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: text.titleSmall),
                Text(body, style: text.bodyMedium),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
