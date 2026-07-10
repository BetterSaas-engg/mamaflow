import 'dart:async';
import 'dart:io' show Platform;

import 'package:firebase_messaging/firebase_messaging.dart';

import 'device_registrar.dart';

/// Owns the app's FCM lifecycle for reminder push (D22/D27): asks for
/// notification permission, obtains the device token, registers it with the
/// backend, re-registers when the token rotates, and unregisters on sign-out
/// so a signed-out (or switched) device stops receiving the previous
/// account's digests.
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
  String? _lastToken;
  StreamSubscription<String>? _refreshSub;

  /// Idempotent within a session: safe to call every time the signed-in shell
  /// mounts. A failed attempt retries on the next app start (a fresh instance)
  /// or after [stop] (a new session, possibly a different account).
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
      _refreshSub = messaging.onTokenRefresh.listen(_register);
    } catch (_) {
      // Best-effort: never surface push-setup failures to the UI. Firebase
      // being unconfigured/unavailable simply means no reminders yet.
    }
  }

  /// Sign-out path: stop listening for token rotation and reset so the next
  /// [start] (same or different account) registers fresh. With
  /// [unregisterFromBackend] the device row is soft-deleted server-side —
  /// skip it on a 401-triggered sign-out, where the JWT is already invalid
  /// and the authed call would just 401 again.
  Future<void> stop({bool unregisterFromBackend = true}) async {
    final token = _lastToken;
    _lastToken = null;
    _started = false;
    await _refreshSub?.cancel();
    _refreshSub = null;

    if (unregisterFromBackend && token != null) {
      try {
        await _registrar.unregister(fcmToken: token);
      } catch (_) {
        // Best-effort: the backend prunes dead tokens, and a later sign-in
        // by anyone on this device reclaims the row via register().
      }
    }
  }

  Future<void> _register(String token) async {
    _lastToken = token;
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
