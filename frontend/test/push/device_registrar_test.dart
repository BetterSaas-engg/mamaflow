import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/core/api_client.dart';
import 'package:mamaflow/push/device_registrar.dart';
import 'package:mocktail/mocktail.dart';

class _MockApi extends Mock implements ApiClient {}

void main() {
  setUpAll(() => registerFallbackValue(<String, dynamic>{}));

  test('registers the device token with the backend', () async {
    final api = _MockApi();
    when(() => api.postJson(any(), any())).thenAnswer((_) async => {'ok': true});
    final registrar = DeviceRegistrar(api);

    await registrar.register(fcmToken: 'FCMTOKEN', platform: 'ios');

    final captured =
        verify(() => api.postJson(captureAny(), captureAny())).captured;
    expect(captured[0], '/api/v1/devices/register');
    expect(captured[1], {'fcm_token': 'FCMTOKEN', 'platform': 'ios'});
  });

  test('unregisters the device token with the backend', () async {
    final api = _MockApi();
    when(() => api.postVoid(any(), any())).thenAnswer((_) async {});
    final registrar = DeviceRegistrar(api);

    await registrar.unregister(fcmToken: 'FCMTOKEN');

    final captured =
        verify(() => api.postVoid(captureAny(), captureAny())).captured;
    expect(captured[0], '/api/v1/devices/unregister');
    expect(captured[1], {'fcm_token': 'FCMTOKEN'});
  });
}
