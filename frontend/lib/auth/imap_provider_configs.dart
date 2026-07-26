import 'package:flutter/material.dart';

/// UI configuration for an app-password (IMAP) sign-in provider.
///
/// Note: Rogers is a CONFIG here but not a backend provider — rogers.com
/// mail is Yahoo-hosted, so its tile submits `provider: 'yahoo'` with
/// Rogers-specific instructions.
class ImapProviderConfig {
  const ImapProviderConfig({
    required this.backendKey,
    required this.title,
    required this.icon,
    required this.steps,
    required this.helpUrl,
    required this.helpUrlLabel,
  });

  /// Value sent as `provider` to POST /api/v1/auth/imap.
  final String backendKey;
  final String title;
  final IconData icon;

  /// Guided "get an app password" steps, shown above the form.
  final List<String> steps;

  /// Where to generate the app password (opened in the external browser).
  final String helpUrl;
  final String helpUrlLabel;
}

const yahooConfig = ImapProviderConfig(
  backendKey: 'yahoo',
  title: 'Yahoo Mail',
  icon: Icons.alternate_email,
  steps: [
    'Sign in to your Yahoo account security page.',
    'Choose "Generate and manage app passwords".',
    'Create one named "Mamaflow" and copy the 16-character password.',
    'Paste it below with your Yahoo email address.',
  ],
  helpUrl: 'https://login.yahoo.com/myaccount/security/app-password',
  helpUrlLabel: 'Open Yahoo app passwords',
);

const rogersConfig = ImapProviderConfig(
  backendKey: 'yahoo', // Rogers email is Yahoo-hosted
  title: 'Rogers Mail',
  icon: Icons.alternate_email,
  steps: [
    'Rogers email is powered by Yahoo — sign in with your @rogers.com '
        'address on the Yahoo account security page.',
    'Choose "Generate and manage app passwords".',
    'Create one named "Mamaflow" and copy the 16-character password.',
    'Paste it below with your @rogers.com email address.',
  ],
  helpUrl: 'https://login.yahoo.com/myaccount/security/app-password',
  helpUrlLabel: 'Open Yahoo app passwords',
);

const icloudConfig = ImapProviderConfig(
  backendKey: 'icloud',
  title: 'iCloud Mail',
  icon: Icons.cloud_outlined,
  steps: [
    'Go to your Apple Account page (account.apple.com) and sign in.',
    'Open Sign-In and Security → App-Specific Passwords '
        '(two-factor authentication must be on).',
    'Create one named "Mamaflow" and copy it.',
    'Paste it below with your primary iCloud email address.',
  ],
  helpUrl: 'https://account.apple.com/account/manage',
  helpUrlLabel: 'Open Apple Account settings',
);

const imapProviderConfigs = [yahooConfig, rogersConfig, icloudConfig];
