import '../core/api_client.dart';

/// Triggers a server-side inbox sync (fetch -> blocklist -> redact -> extract
/// -> persist) for the authenticated user. POST /api/v1/sync; the user is
/// derived from the JWT, so the body is empty.
class SyncService {
  SyncService(this._api);

  final ApiClient _api;

  /// Returns the number of newly-created items.
  Future<int> run() async {
    final resp = await _api.postJson('/api/v1/sync', const <String, dynamic>{});
    return (resp['items_created'] as num?)?.toInt() ?? 0;
  }
}
