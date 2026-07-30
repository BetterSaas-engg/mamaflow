import '../core/api_client.dart';

/// One connected mailbox.
class Mailbox {
  const Mailbox({required this.id, required this.provider, required this.email});

  final String id;
  final String provider;
  final String email;

  static Mailbox fromJson(Map<String, dynamic> json) => Mailbox(
        id: json['id'] as String? ?? '',
        provider: json['provider'] as String? ?? '',
        email: json['email'] as String? ?? '',
      );

  /// Provider display name. Falls back to the raw key rather than hiding an
  /// unknown provider — the registry can grow server-side ahead of the app.
  String get providerLabel => switch (provider) {
        'google' => 'Gmail',
        'yahoo' => 'Yahoo',
        'icloud' => 'iCloud',
        'microsoft' => 'Outlook',
        _ => provider,
      };
}

/// The account's plan and what it allows.
///
/// Every limit here is computed by the server. The app deliberately does not
/// derive entitlements from the tier string: duplicating that logic client-side
/// is how the two definitions drift the moment pricing changes, and a stale
/// build would then show the wrong limit.
class AccountPlan {
  const AccountPlan({
    required this.tier,
    required this.adsEnabled,
    required this.memberLimit,
    required this.mailboxesConnected,
    required this.mailboxLimit,
    required this.canAddMailbox,
  });

  final String tier;
  final bool adsEnabled;
  final int memberLimit;
  final int mailboxesConnected;
  final int mailboxLimit;
  final bool canAddMailbox;

  static AccountPlan fromJson(Map<String, dynamic> json) {
    final mailboxes = (json['mailboxes'] as Map?)?.cast<String, dynamic>() ?? {};
    return AccountPlan(
      tier: json['tier'] as String? ?? 'free',
      adsEnabled: json['ads_enabled'] as bool? ?? true,
      memberLimit: json['member_limit'] as int? ?? 1,
      mailboxesConnected: mailboxes['connected'] as int? ?? 0,
      mailboxLimit: mailboxes['limit'] as int? ?? 1,
      canAddMailbox: mailboxes['can_add_another'] as bool? ?? false,
    );
  }

  String get tierLabel => switch (tier) {
        'pro' => 'Pro',
        'family' => 'Family',
        _ => 'Free',
      };
}

/// Raised when the backend refuses a mailbox for a reason the user can act on.
class MailboxException implements Exception {
  const MailboxException(this.message);
  final String message;
  @override
  String toString() => message;
}

class MailboxService {
  MailboxService(this._api);

  final ApiClient _api;

  Future<AccountPlan> plan() async =>
      AccountPlan.fromJson(await _api.getJson('/api/v1/account/me'));

  Future<List<Mailbox>> list() async {
    final raw = await _api.getJsonList('/api/v1/account/mailboxes');
    return raw.map((e) => Mailbox.fromJson(e)).toList();
  }

  /// Connect another IMAP mailbox (Yahoo/Rogers/iCloud).
  Future<Mailbox> addImap({
    required String provider,
    required String email,
    required String appPassword,
  }) async {
    final json = await _api.postJson('/api/v1/account/mailboxes', {
      'provider': provider,
      'email': email,
      'app_password': appPassword,
    });
    return Mailbox.fromJson(json);
  }

  /// Connect another Gmail. The address is taken from Google's verified token
  /// server-side, so nothing here names the mailbox.
  Future<Mailbox> addGoogle({
    required String code,
    required String codeVerifier,
  }) async {
    final json = await _api.postJson('/api/v1/account/mailboxes/google', {
      'code': code,
      'code_verifier': codeVerifier,
    });
    return Mailbox.fromJson(json);
  }

  Future<void> remove(String id) =>
      _api.delete('/api/v1/account/mailboxes/$id');
}
