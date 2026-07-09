import 'dart:io' show Platform;

import 'package:firebase_messaging/firebase_messaging.dart';

import 'device_registrar.dart';

/// Owns the app's FCM lifecycle for reminder push (D22/D27): asks for
/// notification permission, obtains the device token, registers it with the
/// backend, and re-registers when the token rotates.
///
/// Every step is best-effort — a failure here must never crash or block the
/// signed-in UI. The token is not content and is not a credential; the backend
/// stores it only to address reminder pushes to this device.
class PushService {
  final DeviceRegistrar _registrar;
  final FirebaseMessaging? _injected;

  /// [messaging] is injectable for tests; production resolves
  /// [FirebaseMessaging.instance] lazily inside [start] so constructing the
  /// service (e.g. via a provider in a widget test) never touches Firebase.
  PushService(this._registrar, {FirebaseMessaging? messaging})
      : _injected = messaging;

  bool _started = false;

  /// Idempotent within a session: safe to call every time the signed-in shell
  /// mounts. A failed attempt retries on the next app start (a fresh instance).
  Future<void> start() async {
    if (_started) return;
    _started = true;

    try {
      final messaging = _injected ?? FirebaseMessaging.instance;

      await messaging.requestPermission();

      // Show the reminder as a banner even if the app is foregrounded on iOS;
      // Android surfaces FCM notification messages via the system tray.
      await messaging.setForegroundNotificationPresentationOptions(
        alert: true,
        badge: true,
        sound: true,
      );

      final token = await messaging.getToken();
      if (token != null) await _register(token);

      // A rotated token would otherwise silently stop reminders reaching us.
      messaging.onTokenRefresh.listen(_register);
    } catch (_) {
      // Best-effort: never surface push-setup failures to the UI. Firebase
      // being unconfigured/unavailable simply means no reminders yet.
    }
  }

  Future<void> _register(String token) async {
    try {
      await _registrar.register(
        fcmToken: token,
        platform: Platform.isIOS ? 'ios' : 'android',
      );
    } catch (_) {
      // Best-effort: retried on the next token refresh or app start.
    }
  }
}
