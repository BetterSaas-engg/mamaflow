import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/core/api_client.dart';
import 'package:mamaflow/items/sync_service.dart';
import 'package:mocktail/mocktail.dart';

class _MockApi extends Mock implements ApiClient {}

void main() {
  setUpAll(() => registerFallbackValue(<String, dynamic>{}));

  test('runUntilDone starts the sync then polls status to completion', () async {
    final api = _MockApi();
    when(() => api.postJson(any(), any()))
        .thenAnswer((_) async => {'status': 'started'});
    final statuses = [
      {'status': 'running'},
      {'status': 'running'},
      {'status': 'done', 'items_created': 3, 'messages_scanned': 10},
    ];
    when(() => api.getJson(any())).thenAnswer((_) async => statuses.removeAt(0));

    final svc = SyncService(api);
    final created = await svc.runUntilDone(pollInterval: Duration.zero);

    expect(created, 3);
    final posted = verify(() => api.postJson(captureAny(), any())).captured;
    expect(posted.single, '/api/v1/sync');
    verify(() => api.getJson('/api/v1/sync/status')).called(3);
  });

  test('runUntilDone throws SyncFailedException when the server reports failed', () async {
    final api = _MockApi();
    when(() => api.postJson(any(), any()))
        .thenAnswer((_) async => {'status': 'started'});
    when(() => api.getJson(any()))
        .thenAnswer((_) async => {'status': 'failed', 'error': 'Sync failed. Try again.'});

    final svc = SyncService(api);

    await expectLater(
      svc.runUntilDone(pollInterval: Duration.zero),
      throwsA(isA<SyncFailedException>()),
    );
  });

  test('runUntilDone tolerates already_running (just polls)', () async {
    final api = _MockApi();
    when(() => api.postJson(any(), any()))
        .thenAnswer((_) async => {'status': 'already_running'});
    when(() => api.getJson(any()))
        .thenAnswer((_) async => {'status': 'done', 'items_created': 0});

    final svc = SyncService(api);
    final created = await svc.runUntilDone(pollInterval: Duration.zero);

    expect(created, 0);
  });

  test('a 429 cooldown becomes a friendly SyncFailedException', () async {
    final api = _MockApi();
    final opts = RequestOptions(path: '/api/v1/sync');
    when(() => api.postJson(any(), any())).thenThrow(DioException(
      requestOptions: opts,
      response: Response(requestOptions: opts, statusCode: 429),
    ));

    final svc = SyncService(api);

    await expectLater(
      svc.runUntilDone(pollInterval: Duration.zero),
      throwsA(isA<SyncFailedException>().having(
          (e) => e.message, 'message', contains('recently'))),
    );
    verifyNever(() => api.getJson(any())); // no pointless polling after 429
  });

  test('runUntilDone gives up after maxPolls', () async {
    final api = _MockApi();
    when(() => api.postJson(any(), any()))
        .thenAnswer((_) async => {'status': 'started'});
    when(() => api.getJson(any())).thenAnswer((_) async => {'status': 'running'});

    final svc = SyncService(api);

    await expectLater(
      svc.runUntilDone(pollInterval: Duration.zero, maxPolls: 5),
      throwsA(isA<SyncFailedException>()),
    );
    verify(() => api.getJson(any())).called(5);
  });
}
