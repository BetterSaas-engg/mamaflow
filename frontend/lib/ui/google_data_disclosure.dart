import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../theme/tokens.dart';

/// The privacy policy, on the same domain as the homepage (a Google
/// verification requirement — see docs/e0-oauth-verification.md).
const kPrivacyPolicyUrl = 'https://themamaflow.com/privacy.html';

/// In-app disclosure shown immediately before the Google OAuth consent screen.
///
/// Required by Google's Workspace user data and developer policy for restricted
/// scopes, and a documented cause of verification rejection when missing. The
/// policy's constraints are specific, so this widget is shaped by them rather
/// than by taste:
///
///  - it must IMMEDIATELY precede the consent request (so it is presented by
///    the sign-in action, not buried in onboarding or a settings page);
///  - it must state what is accessed, how it is used, and how it is shared —
///    and it "cannot be placed only in a privacy policy or terms of service",
///    which is why the substance is inline here rather than behind the link;
///  - it must carry the Limited Use adherence statement;
///  - it requires AFFIRMATIVE action, and navigating away must not count as
///    consent — hence `barrierDismissible: false`, `PopScope`, and a result
///    that is only ever true via the explicit button;
///  - it must not auto-dismiss or expire.
///
/// Scoped to Google deliberately: IMAP providers (D38) are not Google user data,
/// and citing Google's policy to an iCloud user would simply be wrong.
///
/// Returns true only if the user explicitly agreed.
Future<bool> showGoogleDataDisclosure(BuildContext context) async {
  final agreed = await showDialog<bool>(
    context: context,
    barrierDismissible: false, // dismissal is not consent
    builder: (_) => const _GoogleDataDisclosureDialog(),
  );
  return agreed == true;
}

class _GoogleDataDisclosureDialog extends StatelessWidget {
  const _GoogleDataDisclosureDialog();

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final scheme = Theme.of(context).colorScheme;
    return PopScope(
      // Back-gesture/button leaves without consenting rather than returning a
      // value the caller could mistake for agreement.
      canPop: true,
      child: AlertDialog(
        title: const Text('Before you connect Gmail'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const _Point(
                icon: Icons.mark_email_read_outlined,
                title: 'What we read',
                body: 'Mamaflow reads recent messages in your Gmail, '
                    'read-only. We can never send, change, or delete anything.',
              ),
              const _Point(
                icon: Icons.event_available_outlined,
                title: 'What we do with it',
                body: 'We find your family\'s events, appointments and '
                    'to-dos — school notices, medical appointments, '
                    'activities — and turn them into your calendar and '
                    'reminders.',
              ),
              const _Point(
                icon: Icons.share_outlined,
                title: 'Who else sees it',
                body: 'Message text is sent to our AI provider (Anthropic) to '
                    'pick out those details, after personal information is '
                    'removed. They do not use it to train their models. We '
                    'never sell your data.',
              ),
              const _Point(
                icon: Icons.lock_outline,
                title: 'What we never do',
                body: 'We never store the raw text of your email, and we never '
                    'use your email — or anything learned from it — for '
                    'advertising.',
              ),
              const SizedBox(height: AppSpacing.md),
              Text(
                "Mamaflow's use and transfer of information received from "
                'Google APIs adheres to the Google API Services User Data '
                'Policy, including the Limited Use requirements.',
                style: text.bodySmall?.copyWith(color: scheme.onSurfaceVariant),
              ),
              const SizedBox(height: AppSpacing.md),
              TextButton(
                onPressed: () => launchUrl(
                  Uri.parse(kPrivacyPolicyUrl),
                  mode: LaunchMode.externalApplication,
                ),
                child: const Text('Read the full privacy policy'),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Not now'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('I agree, continue'),
          ),
        ],
      ),
    );
  }
}

class _Point extends StatelessWidget {
  const _Point({required this.icon, required this.title, required this.body});
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
                const SizedBox(height: 2),
                Text(body, style: text.bodyMedium),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
