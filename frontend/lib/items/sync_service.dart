import 'package:dio/dio.dart';

import '../core/api_client.dart';

class SyncFailedException implements Exception {
  const SyncFailedException(this.message);
  final String message;
  @override
  String toString() => 'SyncFailedException: $message';
}

/// Triggers a server-side inbox sync and polls it to completion. The sync runs
/// as a backend background task (POST /api/v1/sync -> 202 started); progress is
/// read from GET /api/v1/sync/status until done/failed.
class SyncService {
  SyncService(this._api);

  final ApiClient _api;

  /// Starts a sync (tolerating one already in flight) and polls until it
  /// finishes. Returns the number of newly created items; throws
  /// [SyncFailedException] on server-reported failure or timeout.
  Future<int> runUntilDone({
    Duration pollInterval = const Duration(seconds: 2),
    int maxPolls = 90,
  }) async {
    try {
      await _api.postJson('/api/v1/sync', const <String, dynamic>{});
    } on DioException catch (e) {
      if (e.response?.statusCode == 429) {
        // Server-side cooldown between syncs (each is a full inbox scan).
        throw const SyncFailedException('Synced recently — try again in a minute.');
      }
      rethrow;
    }

    for (var i = 0; i < maxPolls; i++) {
      if (pollInterval > Duration.zero) {
        await Future<void>.delayed(pollInterval);
      }
      final status = await _api.getJson('/api/v1/sync/status');
      switch (status['status'] as String?) {
        case 'done':
          return (status['items_created'] as num?)?.toInt() ?? 0;
        case 'failed':
          throw SyncFailedException(
              status['error'] as String? ?? 'Sync failed. Try again.');
        default:
          continue; // running (or idle race) — keep polling
      }
    }
    throw const SyncFailedException('Sync timed out. Pull to refresh later.');
  }
}
