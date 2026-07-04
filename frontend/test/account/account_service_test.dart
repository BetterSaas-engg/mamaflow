import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/account/account_service.dart';
import 'package:mamaflow/core/api_client.dart';
import 'package:mocktail/mocktail.dart';

class _MockApi extends Mock implements ApiClient {}

void main() {
  test('deleteAccount calls DELETE /api/v1/account', () async {
    final api = _MockApi();
    when(() => api.delete(any())).thenAnswer((_) async {});

    await AccountService(api).deleteAccount();

    verify(() => api.delete('/api/v1/account')).called(1);
  });
}
