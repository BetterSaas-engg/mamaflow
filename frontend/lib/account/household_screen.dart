import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../theme/tokens.dart';
import 'account_providers.dart';
import 'household.dart';

/// Share the calendar with a partner (Family plan).
class HouseholdScreen extends ConsumerWidget {
  const HouseholdScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final household = ref.watch(householdProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Family sharing')),
      body: household.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (_, _) => const Center(child: Text("Couldn't load this.")),
        data: (h) => ListView(
          padding: const EdgeInsets.all(AppSpacing.lg),
          children: [
            if (!h.sharingAvailable) ...[
              const _Explainer(),
              const SizedBox(height: AppSpacing.lg),
              Text(
                'Family sharing is part of the Family plan. Your plan covers '
                '${h.memberLimit} person.',
                style: Theme.of(context).textTheme.bodyMedium,
              ),
            ] else ...[
              const _Explainer(),
              const SizedBox(height: AppSpacing.lg),
              for (final m in h.members)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: const Icon(Icons.person_outline),
                  title: Text(m.email),
                  subtitle: Text(m.isOwner ? 'Plan owner' : 'Member'),
                  trailing: _canRemove(h, m)
                      ? IconButton(
                          icon: const Icon(Icons.person_remove_outlined),
                          tooltip: 'Remove',
                          onPressed: () => _confirmRemove(context, ref, m),
                        )
                      : null,
                ),
              const SizedBox(height: AppSpacing.md),
              if (h.isOwner || !h.exists)
                FilledButton.icon(
                  onPressed: () => _invite(context, ref),
                  icon: const Icon(Icons.person_add_alt),
                  label: Text(
                    h.members.length > 1 ? 'Invite someone else' : 'Invite my partner',
                  ),
                ),
              if (!h.exists) ...[
                const SizedBox(height: AppSpacing.lg),
                OutlinedButton(
                  onPressed: () => _enterCode(context, ref),
                  child: const Text('I have a code'),
                ),
              ],
            ],
          ],
        ),
      ),
    );
  }

  /// The owner can remove others; anyone can remove themselves. Nobody can
  /// remove the owner — that would strand the plan.
  bool _canRemove(HouseholdView h, HouseholdMember m) => !m.isOwner;

  Future<void> _invite(BuildContext context, WidgetRef ref) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      final invite = await ref.read(householdServiceProvider).invite();
      ref.invalidate(householdProvider);
      if (!context.mounted) return;
      await showDialog<void>(
        context: context,
        builder: (_) => AlertDialog(
          title: const Text('Share this code'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Send this to your partner. They enter it under Family '
                'sharing to join. It works once, and expires in 14 days.',
              ),
              const SizedBox(height: AppSpacing.lg),
              SelectableText(
                invite.code,
                style: Theme.of(context).textTheme.headlineSmall,
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () {
                Clipboard.setData(ClipboardData(text: invite.code));
                Navigator.of(context).pop();
              },
              child: const Text('Copy'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Done'),
            ),
          ],
        ),
      );
    } on DioException catch (e) {
      messenger.showSnackBar(SnackBar(content: Text(_detail(e))));
    }
  }

  Future<void> _enterCode(BuildContext context, WidgetRef ref) async {
    final controller = TextEditingController();
    final messenger = ScaffoldMessenger.of(context);
    final code = await showDialog<String>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Join a family'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Say plainly what joining exposes. Since the extractor captures
            // every appointment — work ones included — this is not obvious,
            // and consent has to be informed.
            const Text(
              'Joining shares the events found in your email with the other '
              'person, and shows you theirs. Your inbox and password stay '
              'private — only the events are shared.',
            ),
            const SizedBox(height: AppSpacing.lg),
            TextField(
              controller: controller,
              autocorrect: false,
              textCapitalization: TextCapitalization.characters,
              decoration: const InputDecoration(labelText: 'Invite code'),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(controller.text.trim()),
            child: const Text('Join'),
          ),
        ],
      ),
    );
    if (code == null || code.isEmpty) return;
    try {
      await ref.read(householdServiceProvider).accept(code);
      ref.invalidate(householdProvider);
      ref.invalidate(accountPlanProvider);
    } on DioException catch (e) {
      messenger.showSnackBar(SnackBar(content: Text(_detail(e))));
    }
  }

  Future<void> _confirmRemove(
    BuildContext context,
    WidgetRef ref,
    HouseholdMember member,
  ) async {
    final messenger = ScaffoldMessenger.of(context);
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Stop sharing?'),
        content: Text(
          "You'll stop seeing ${member.email}'s events and they'll stop "
          'seeing yours. Nothing is deleted.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Stop sharing'),
          ),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await ref.read(householdServiceProvider).remove(member.id);
      ref.invalidate(householdProvider);
    } on DioException catch (e) {
      messenger.showSnackBar(SnackBar(content: Text(_detail(e))));
    }
  }

  /// Prefer the backend's message: it distinguishes a full household from a
  /// bad code from a plan that doesn't include sharing.
  String _detail(DioException e) {
    final data = e.response?.data;
    if (data is Map && data['detail'] is String) return data['detail'] as String;
    return 'Something went wrong. Try again.';
  }
}

class _Explainer extends StatelessWidget {
  const _Explainer();

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.groups_outlined, color: scheme.primary),
              const SizedBox(width: AppSpacing.sm),
              Text('One calendar, both parents',
                  style: Theme.of(context).textTheme.titleSmall),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          const Text(
            'You each keep your own sign-in and your own email accounts. '
            'Only the events we find are shared — never your inbox or your '
            'password.',
          ),
        ],
      ),
    );
  }
}
