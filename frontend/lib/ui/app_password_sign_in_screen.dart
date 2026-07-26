import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../auth/imap_provider_configs.dart';
import '../auth/session_controller.dart';
import '../theme/tokens.dart';

/// Email + app-password sign-in for IMAP providers (Yahoo/Rogers, iCloud).
/// The app password lives only in this widget's state for the duration of the
/// request — it is never written to the token store or secure storage (D4).
class AppPasswordSignInScreen extends ConsumerStatefulWidget {
  const AppPasswordSignInScreen({super.key, required this.config});
  final ImapProviderConfig config;

  @override
  ConsumerState<AppPasswordSignInScreen> createState() =>
      _AppPasswordSignInScreenState();
}

class _AppPasswordSignInScreenState
    extends ConsumerState<AppPasswordSignInScreen> {
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

  Future<void> _openHelp() async {
    final uri = Uri.parse(widget.config.helpUrl);
    if (!await launchUrl(uri, mode: LaunchMode.externalApplication)) {
      if (mounted) setState(() => _error = 'Could not open the link.');
    }
  }

  Future<void> _submit() async {
    final email = _email.text.trim();
    final password = _password.text;
    if (email.isEmpty || password.isEmpty) {
      setState(() => _error = 'Enter your email and app password.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref.read(sessionProvider.notifier).signInWithAppPassword(
            provider: widget.config.backendKey,
            email: email,
            appPassword: password,
          );
      // Success flips the session; the auth gate (above this pushed route)
      // rebuilds into the home shell — pop back to it.
      if (mounted) Navigator.of(context).popUntil((r) => r.isFirst);
    } catch (e) {
      // AuthException.message carries the backend's user-actionable detail.
      final message = e is Exception ? e.toString() : 'Sign-in failed.';
      if (mounted) {
        setState(() => _error =
            message.replaceFirst('AuthException: ', ''));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final cfg = widget.config;
    final scheme = Theme.of(context).colorScheme;
    final text = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(title: Text('Connect ${cfg.title}')),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(AppSpacing.xl),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(AppSpacing.lg),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Get an app password', style: text.titleMedium),
                      const SizedBox(height: AppSpacing.sm),
                      for (var i = 0; i < cfg.steps.length; i++)
                        Padding(
                          padding: const EdgeInsets.only(bottom: AppSpacing.xs),
                          child: Text('${i + 1}. ${cfg.steps[i]}',
                              style: text.bodyMedium),
                        ),
                      const SizedBox(height: AppSpacing.sm),
                      OutlinedButton.icon(
                        onPressed: _openHelp,
                        icon: const Icon(Icons.open_in_new),
                        label: Text(cfg.helpUrlLabel),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: AppSpacing.lg),
              TextField(
                controller: _email,
                keyboardType: TextInputType.emailAddress,
                autocorrect: false,
                enableSuggestions: false,
                decoration: InputDecoration(
                  labelText: '${cfg.title} email',
                  hintText: 'you@example.com',
                ),
              ),
              const SizedBox(height: AppSpacing.md),
              TextField(
                controller: _password,
                obscureText: true,
                autocorrect: false,
                enableSuggestions: false,
                decoration: const InputDecoration(
                  labelText: 'App password',
                  hintText: '16-character app password',
                ),
              ),
              if (_error != null) ...[
                const SizedBox(height: AppSpacing.md),
                Text(_error!,
                    style: text.bodyMedium?.copyWith(color: scheme.error)),
              ],
              const SizedBox(height: AppSpacing.lg),
              SizedBox(
                width: double.infinity,
                child: FilledButton(
                  onPressed: _busy ? null : _submit,
                  child: _busy
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Text('Connect'),
                ),
              ),
              const SizedBox(height: AppSpacing.md),
              Text(
                'We only read your email to find family events. Your app '
                'password is stored securely and never shared.',
                style: text.bodySmall?.copyWith(color: scheme.onSurfaceVariant),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
