import 'dart:async';

import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/push/device_registrar.dart';
import 'package:mamaflow/push/push_service.dart';
import 'package:mocktail/mocktail.dart';

class _MockRegistrar extends Mock implements DeviceRegistrar {}

class _MockMessaging extends Mock implements FirebaseMessaging {}

class _MockSettings extends Mock implements NotificationSettings {}

void main() {
  late _MockRegistrar registrar;
  late _MockMessaging messaging;
  late StreamController<String> refresh;
  late PushService service;

  setUp(() {
    registrar = _MockRegistrar();
    messaging = _MockMessaging();
    refresh = StreamController<String>.broadcast();
    when(() => messaging.requestPermission())
        .thenAnswer((_) async => _MockSettings());
    when(() => messaging.setForegroundNotificationPresentationOptions(
          alert: true,
          badge: true,
          sound: true,
        )).thenAnswer((_) async {});
    when(() => messaging.getToken()).thenAnswer((_) async => 'tok-1');
    when(() => messaging.onTokenRefresh).thenAnswer((_) => refresh.stream);
    when(() => registrar.register(
          fcmToken: any(named: 'fcmToken'),
          platform: any(named: 'platform'),
        )).thenAnswer((_) async {});
    when(() => registrar.unregister(fcmToken: any(named: 'fcmToken')))
        .thenAnswer((_) async {});
    service = PushService(registrar, messaging: messaging);
  });

  tearDown(() => refresh.close());

  test('start registers the current token', () async {
    await service.start();

    verify(() => registrar.register(
          fcmToken: 'tok-1',
          platform: any(named: 'platform'),
        )).called(1);
  });

  test('start after stop re-registers (account switch on a shared device)',
      () async {
    await service.start();
    await service.stop();
    await service.start();

    verify(() => registrar.register(
          fcmToken: 'tok-1',
          platform: any(named: 'platform'),
        )).called(2);
  });

  test('stop unregisters the last registered token from the backend',
      () async {
    await service.start();
    await service.stop();

    verify(() => registrar.unregister(fcmToken: 'tok-1')).called(1);
  });

  test('stop without a registered token makes no unregister call', () async {
    await service.stop();

    verifyNever(() => registrar.unregister(fcmToken: any(named: 'fcmToken')));
  });

  test('stop(unregisterFromBackend: false) skips the network call but resets',
      () async {
    await service.start();
    await service.stop(unregisterFromBackend: false);

    verifyNever(() => registrar.unregister(fcmToken: any(named: 'fcmToken')));

    await service.start();
    verify(() => registrar.register(
          fcmToken: 'tok-1',
          platform: any(named: 'platform'),
        )).called(2);
  });

  test('a rotated token is re-registered while started', () async {
    await service.start();
    refresh.add('tok-2');
    await pumpEventQueue();

    verify(() => registrar.register(
          fcmToken: 'tok-2',
          platform: any(named: 'platform'),
        )).called(1);
  });

  test('stop cancels the token-refresh listener', () async {
    await service.start();
    await service.stop();
    refresh.add('tok-2');
    await pumpEventQueue();

    verifyNever(() => registrar.register(
          fcmToken: 'tok-2',
          platform: any(named: 'platform'),
        ));
  });

  test('stop is best-effort when the backend unregister fails', () async {
    when(() => registrar.unregister(fcmToken: any(named: 'fcmToken')))
        .thenThrow(Exception('network down'));
    await service.start();

    await expectLater(service.stop(), completes);
  });
}
