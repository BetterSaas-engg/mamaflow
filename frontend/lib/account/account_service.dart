import '../core/api_client.dart';

/// Deletes the signed-in user's account (soft-delete + Gmail revocation
/// server-side). The caller signs out afterward.
class AccountService {
  AccountService(this._api);
  final ApiClient _api;

  Future<void> deleteAccount() => _api.delete('/api/v1/account');
}
