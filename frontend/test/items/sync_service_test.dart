import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/core/api_client.dart';
import 'package:mamaflow/items/sync_service.dart';
import 'package:mocktail/mocktail.dart';

class _MockApi extends Mock implements ApiClient {}

void main() {
  setUpAll(() => registerFallbackValue(<String, dynamic>{}));

  test('run() POSTs /api/v1/sync and returns items_created', () async {
    final api = _MockApi();
    when(() => api.postJson(any(), any())).thenAnswer((_) async => {
          'messages_scanned': 12,
          'blocked': 3,
          'processed': 9,
          'items_created': 5,
        });
    final svc = SyncService(api);

    final created = await svc.run();

    expect(created, 5);
    final captured = verify(() => api.postJson(captureAny(), captureAny())).captured;
    expect(captured[0], '/api/v1/sync');
    expect(captured[1], <String, dynamic>{});
  });
}
