import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../auth/session_controller.dart';
import '../theme/app_logo.dart';
import '../theme/tokens.dart';

/// Shown when no session JWT is present. The single action runs the mobile
/// Google sign-in -> backend exchange -> JWT store flow (logic unchanged).
class SignInScreen extends ConsumerStatefulWidget {
  const SignInScreen({super.key});

  @override
  ConsumerState<SignInScreen> createState() => _SignInScreenState();
}

class _SignInScreenState extends ConsumerState<SignInScreen> {
  bool _busy = false;
  String? _error;

  Future<void> _signIn() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref.read(sessionProvider.notifier).signIn();
      // On success the auth gate swaps to the home screen automatically.
    } catch (e) {
      // Debug-only diagnostic: error type + message (never tokens/PII — the
      // exchange error paths carry no credential material).
      debugPrint('sign-in failed: ${e.runtimeType}: $e');
      if (mounted) setState(() => _error = 'Sign-in failed. Please try again.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final text = Theme.of(context).textTheme;
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(AppSpacing.xl),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const AppLogo(size: 104)
                    .animate()
                    .fadeIn(duration: AppDurations.slow)
                    .scale(begin: const Offset(0.8, 0.8), curve: AppCurves.standard),
                const SizedBox(height: AppSpacing.lg),
                Text('Mamaflow', style: text.displaySmall),
                const SizedBox(height: AppSpacing.sm),
                Text(
                  'Your family calendar, from your inbox.',
                  style: text.bodyLarge?.copyWith(color: scheme.onSurfaceVariant),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: AppSpacing.xl),
                const _TrustLine(
                    icon: Icons.mark_email_read_outlined,
                    text: 'Turns your inbox into a family calendar'),
                const SizedBox(height: AppSpacing.md),
                const _TrustLine(
                    icon: Icons.lock_outline,
                    text: 'Private by design — your email is never used for ads'),
                const SizedBox(height: AppSpacing.md),
                const _TrustLine(
                    icon: Icons.auto_awesome_outlined,
                    text: 'Free, with an ad-free option'),
                const SizedBox(height: AppSpacing.xl),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton.icon(
                    onPressed: _busy ? null : _signIn,
                    icon: _busy
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.login),
                    label: const Text('Continue with Google'),
                  ),
                ),
                if (_error != null) ...[
                  const SizedBox(height: AppSpacing.lg),
                  Text(_error!,
                      style: text.bodyMedium?.copyWith(color: scheme.error),
                      textAlign: TextAlign.center),
                ],
                const SizedBox(height: AppSpacing.xl),
                Text(
                  'We only read your email to find family events. Nothing is shared.',
                  style: text.bodySmall?.copyWith(color: scheme.onSurfaceVariant),
                  textAlign: TextAlign.center,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _TrustLine extends StatelessWidget {
  const _TrustLine({required this.icon, required this.text});
  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final style = Theme.of(context).textTheme;
    return Row(
      children: [
        Icon(icon, size: 20, color: scheme.primary),
        const SizedBox(width: AppSpacing.md),
        Expanded(child: Text(text, style: style.bodyMedium)),
      ],
    );
  }
}
