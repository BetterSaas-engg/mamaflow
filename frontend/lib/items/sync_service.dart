import 'package:dio/dio.dart';

import '../core/api_client.dart';

class SyncFailedException implements Exception {
  const SyncFailedException(this.message);
  final String message;
  @override
  String toString() => 'SyncFailedException: $message';
}

/// A point-in-time view of the server-side sync, parsed from GET /sync/status.
class SyncStatus {
  const SyncStatus({
    required this.status,
    this.messagesScanned,
    this.toProcess,
    this.processed,
    this.itemsCreated,
    this.error,
  });

  final String status; // idle | running | done | failed
  final int? messagesScanned;
  final int? toProcess;
  final int? processed;
  final int? itemsCreated;
  final String? error;

  factory SyncStatus.fromJson(Map<String, dynamic> j) => SyncStatus(
        status: j['status'] as String? ?? 'idle',
        messagesScanned: (j['messages_scanned'] as num?)?.toInt(),
        toProcess: (j['to_process'] as num?)?.toInt(),
        processed: (j['processed'] as num?)?.toInt(),
        itemsCreated: (j['items_created'] as num?)?.toInt(),
        error: j['error'] as String?,
      );
}

/// Triggers a server-side inbox sync and polls it to completion.
class SyncService {
  SyncService(this._api);
  final ApiClient _api;

  /// Starts a sync and yields each polled status until it finishes. Throws
  /// [SyncFailedException] on a cooldown (429) or timeout.
  Stream<SyncStatus> run({
    Duration pollInterval = const Duration(seconds: 2),
    int maxPolls = 90,
  }) async* {
    try {
      await _api.postJson('/api/v1/sync', const <String, dynamic>{});
    } on DioException catch (e) {
      if (e.response?.statusCode == 429) {
        throw const SyncFailedException('Synced recently — try again in a minute.');
      }
      rethrow;
    }
    for (var i = 0; i < maxPolls; i++) {
      if (pollInterval > Duration.zero) {
        await Future<void>.delayed(pollInterval);
      }
      final status = SyncStatus.fromJson(await _api.getJson('/api/v1/sync/status'));
      yield status;
      if (status.status == 'done' || status.status == 'failed') return;
    }
    throw const SyncFailedException('Sync timed out. Pull to refresh later.');
  }

  /// Drains [run] and returns the number of newly created items; throws
  /// [SyncFailedException] on server-reported failure or timeout.
  Future<int> runUntilDone({
    Duration pollInterval = const Duration(seconds: 2),
    int maxPolls = 90,
  }) async {
    var created = 0;
    await for (final s in run(pollInterval: pollInterval, maxPolls: maxPolls)) {
      if (s.status == 'failed') {
        throw SyncFailedException(s.error ?? 'Sync failed. Try again.');
      }
      created = s.itemsCreated ?? created;
    }
    return created;
  }
}
