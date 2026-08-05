import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../auth/imap_provider_configs.dart';
import '../theme/tokens.dart';
import 'account_providers.dart';
import 'mailboxes.dart';

/// Manage the mailboxes feeding the calendar, and show what the plan allows.
///
/// The plan's limits are never computed here — they come from the server, so
/// the number shown and the number enforced can't disagree.
class MailboxesScreen extends ConsumerWidget {
  const MailboxesScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final plan = ref.watch(accountPlanProvider);
    final mailboxes = ref.watch(mailboxListProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Email accounts')),
      body: RefreshIndicator(
        onRefresh: () async {
          ref.invalidate(accountPlanProvider);
          ref.invalidate(mailboxListProvider);
        },
        child: mailboxes.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (_, _) => ListView(
            children: const [
              SizedBox(height: AppSpacing.xl),
              Center(child: Text("Couldn't load your email accounts.")),
            ],
          ),
          data: (list) => ListView(
            children: [
              plan.maybeWhen(
                data: (p) => _PlanHeader(plan: p),
                orElse: () => const SizedBox.shrink(),
              ),
              const Divider(height: 1),
              for (final m in list)
                ListTile(
                  leading: const Icon(Icons.mark_email_read_outlined),
                  title: Text(m.email),
                  subtitle: Text(m.providerLabel),
                  trailing: IconButton(
                    icon: const Icon(Icons.link_off),
                    tooltip: 'Disconnect',
                    onPressed: () => _confirmDisconnect(context, ref, m),
                  ),
                ),
              if (list.isEmpty)
                const Padding(
                  padding: EdgeInsets.all(AppSpacing.xl),
                  child: Text(
                    'No email connected, so nothing is being scanned for '
                    'events yet.',
                    textAlign: TextAlign.center,
                  ),
                ),
              const Divider(height: 1),
              plan.maybeWhen(
                data: (p) => _AddMailboxTile(plan: p),
                orElse: () => const SizedBox.shrink(),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _confirmDisconnect(
    BuildContext context,
    WidgetRef ref,
    Mailbox mailbox,
  ) async {
    final messenger = ScaffoldMessenger.of(context);
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Disconnect this email?'),
        content: Text(
          "We'll stop reading ${mailbox.email} and delete the password you "
          'gave us for it. Events already found stay in your calendar.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Disconnect'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await ref.read(mailboxServiceProvider).remove(mailbox.id);
      ref.invalidate(mailboxListProvider);
      ref.invalidate(accountPlanProvider);
    } catch (_) {
      messenger.showSnackBar(
        const SnackBar(content: Text("Couldn't disconnect that email.")),
      );
    }
  }
}

class _PlanHeader extends StatelessWidget {
  const _PlanHeader({required this.plan});
  final AccountPlan plan;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('${plan.tierLabel} plan', style: text.titleMedium),
          const SizedBox(height: AppSpacing.xs),
          Text(
            '${plan.mailboxesConnected} of ${plan.mailboxLimit} email '
            '${plan.mailboxLimit == 1 ? 'account' : 'accounts'} connected',
            style: text.bodyMedium?.copyWith(color: scheme.onSurfaceVariant),
          ),
        ],
      ),
    );
  }
}

class _AddMailboxTile extends ConsumerWidget {
  const _AddMailboxTile({required this.plan});
  final AccountPlan plan;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (!plan.canAddMailbox) {
      // At the limit. Say what the limit IS rather than only that it was hit —
      // and don't dead-end: disconnecting one is the action available today,
      // since there's no purchase flow yet.
      return ListTile(
        leading: const Icon(Icons.lock_outline),
        title: const Text('Add another email'),
        subtitle: Text(
          'Your ${plan.tierLabel} plan includes ${plan.mailboxLimit} '
          '${plan.mailboxLimit == 1 ? 'email account' : 'email accounts'}. '
          'Disconnect one to connect a different one.',
        ),
        enabled: false,
      );
    }
    return ListTile(
      leading: const Icon(Icons.add),
      title: const Text('Add another email'),
      onTap: () => _pickProvider(context, ref),
    );
  }

  Future<void> _pickProvider(BuildContext context, WidgetRef ref) async {
    final config = await showModalBottomSheet<ImapProviderConfig>(
      context: context,
      builder: (_) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            for (final c in imapProviderConfigs)
              ListTile(
                leading: Icon(c.icon),
                title: Text(c.title),
                onTap: () => Navigator.of(context).pop(c),
              ),
          ],
        ),
      ),
    );
    if (config == null || !context.mounted) return;
    final added = await Navigator.of(context).push<bool>(
      MaterialPageRoute(builder: (_) => AddImapMailboxScreen(config: config)),
    );
    if (added == true) {
      ref.invalidate(mailboxListProvider);
      ref.invalidate(accountPlanProvider);
    }
  }
}

/// Connect an additional IMAP mailbox to the CURRENT account.
///
/// Deliberately separate from the sign-in screen of the same shape: that one
/// creates a session, this one attaches a mailbox to the session you already
/// have. Conflating them would make "add a mailbox" indistinguishable from
/// "make a second account".
class AddImapMailboxScreen extends ConsumerStatefulWidget {
  const AddImapMailboxScreen({super.key, required this.config});
  final ImapProviderConfig config;

  @override
  ConsumerState<AddImapMailboxScreen> createState() =>
      _AddImapMailboxScreenState();
}

class _AddImapMailboxScreenState extends ConsumerState<AddImapMailboxScreen> {
  final _email = TextEditingController();
  final _password = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref.read(mailboxServiceProvider).addImap(
            provider: widget.config.backendKey,
            email: _email.text.trim(),
            appPassword: _password.text,
          );
      if (mounted) Navigator.of(context).pop(true);
    } on DioException catch (e) {
      // The backend's message is the useful one — it distinguishes a wrong
      // app password from an over-cap plan from a mailbox already connected
      // elsewhere. Falling back to a generic string would throw that away.
      final detail = (e.response?.data is Map)
          ? (e.response!.data as Map)['detail'] as String?
          : null;
      if (mounted) {
        setState(() => _error = detail ?? "Couldn't connect that email.");
      }
    } catch (_) {
      if (mounted) setState(() => _error = "Couldn't connect that email.");
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('Add ${widget.config.title}')),
      body: ListView(
        padding: const EdgeInsets.all(AppSpacing.lg),
        children: [
          for (final step in widget.config.steps)
            Padding(
              padding: const EdgeInsets.only(bottom: AppSpacing.sm),
              child: Text('• $step'),
            ),
          const SizedBox(height: AppSpacing.lg),
          TextField(
            controller: _email,
            keyboardType: TextInputType.emailAddress,
            autocorrect: false,
            decoration: const InputDecoration(labelText: 'Email address'),
          ),
          const SizedBox(height: AppSpacing.md),
          TextField(
            controller: _password,
            obscureText: true,
            decoration: const InputDecoration(labelText: 'App password'),
          ),
          if (_error != null) ...[
            const SizedBox(height: AppSpacing.md),
            Text(
              _error!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ],
          const SizedBox(height: AppSpacing.lg),
          FilledButton(
            onPressed: _busy ? null : _submit,
            child: _busy
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Text('Connect'),
          ),
        ],
      ),
    );
  }
}
