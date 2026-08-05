import '../core/api_client.dart';

class HouseholdMember {
  const HouseholdMember({
    required this.id,
    required this.email,
    required this.isOwner,
  });

  final String id;
  final String email;
  final bool isOwner;

  static HouseholdMember fromJson(Map<String, dynamic> json) => HouseholdMember(
        id: json['id'] as String? ?? '',
        email: json['email'] as String? ?? '',
        isOwner: json['is_owner'] as bool? ?? false,
      );
}

class HouseholdView {
  const HouseholdView({
    required this.exists,
    required this.isOwner,
    required this.memberLimit,
    required this.members,
    required this.pendingInvites,
  });

  final bool exists;
  final bool isOwner;
  final int memberLimit;
  final List<HouseholdMember> members;
  final int pendingInvites;

  /// Whether this plan supports a second person at all. Family does; free and
  /// pro don't — the server decides, we only render it.
  bool get sharingAvailable => memberLimit > 1;

  static HouseholdView fromJson(Map<String, dynamic> json) => HouseholdView(
        exists: json['exists'] as bool? ?? false,
        isOwner: json['is_owner'] as bool? ?? false,
        memberLimit: json['member_limit'] as int? ?? 1,
        members: ((json['members'] as List?) ?? [])
            .map((e) => HouseholdMember.fromJson(
                Map<String, dynamic>.from(e as Map)))
            .toList(),
        pendingInvites: json['pending_invites'] as int? ?? 0,
      );
}

class HouseholdInvite {
  const HouseholdInvite({required this.code, required this.expiresAt});
  final String code;
  final String expiresAt;

  static HouseholdInvite fromJson(Map<String, dynamic> json) => HouseholdInvite(
        code: json['code'] as String? ?? '',
        expiresAt: json['expires_at'] as String? ?? '',
      );
}

class HouseholdService {
  HouseholdService(this._api);
  final ApiClient _api;

  Future<HouseholdView> get() async =>
      HouseholdView.fromJson(await _api.getJson('/api/v1/account/household'));

  /// Mint a join code. Returned once — the server stores only its hash, so it
  /// cannot be fetched again.
  Future<HouseholdInvite> invite() async => HouseholdInvite.fromJson(
      await _api.postJson('/api/v1/account/household/invites', const {}));

  Future<HouseholdView> accept(String code) async => HouseholdView.fromJson(
      await _api.postJson(
          '/api/v1/account/household/invites/accept', {'code': code}));

  Future<void> remove(String memberId) =>
      _api.delete('/api/v1/account/household/members/$memberId');
}
