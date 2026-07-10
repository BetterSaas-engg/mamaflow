import '../core/api_client.dart';

/// Sends this device's FCM token to the backend so it can deliver reminders
/// (D22). The token itself is fetched via firebase_messaging at app start
/// (wired in Phase 2); this unit only owns the registration call.
class DeviceRegistrar {
  final ApiClient _api;
  DeviceRegistrar(this._api);

  Future<void> register({required String fcmToken, required String platform}) {
    return _api.postJson(
      '/api/v1/devices/register',
      {'fcm_token': fcmToken, 'platform': platform},
    );
  }

  /// Sign-out path: stop the backend addressing reminders to this device.
  Future<void> unregister({required String fcmToken}) {
    return _api.postVoid(
      '/api/v1/devices/unregister',
      {'fcm_token': fcmToken},
    );
  }
}
