import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart' show kIsWeb, kReleaseMode;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../auth/auth_service.dart';
import '../auth/google_auth_codes.dart';
import '../auth/session_controller.dart';
import '../auth/token_store.dart';
import '../push/device_registrar.dart';
import '../push/push_service.dart';
import 'api_client.dart';

const _definedBaseUrl = String.fromEnvironment('API_BASE_URL');
const _devFallbackUrl = 'http://localhost:8000';

/// Resolve + validate the API base URL. A release build without the
/// --dart-define would silently point at localhost, and a cleartext URL would
/// ship without TLS — both are build mistakes, so fail loudly (mirroring the
/// GOOGLE_IOS_CLIENT_ID guard in google_auth_codes.dart).
String resolveBaseUrl(
    {String defined = _definedBaseUrl, bool isRelease = kReleaseMode}) {
  if (defined.isEmpty) {
    if (isRelease) {
      throw StateError(
        'API_BASE_URL is not set. Release builds need '
        '--dart-define=API_BASE_URL=https://<backend host>.',
      );
    }
    return _devFallbackUrl;
  }
  if (isRelease && !defined.startsWith('https://')) {
    throw StateError('API_BASE_URL must be https in release builds.');
  }
  return defined;
}

/// The app's one Dio: bounded timeouts so a dead network fails a request
/// instead of hanging a status poll (and its progress UI) forever.
/// Connect is 30s: slow cellular and the Android emulator's NAT both
/// routinely exceed 10s on a cold TLS connect (observed 2026-07-15).
Dio buildDio({String? baseUrl}) => Dio(BaseOptions(
      baseUrl: baseUrl ?? resolveBaseUrl(),
      connectTimeout: const Duration(seconds: 30),
      receiveTimeout: const Duration(seconds: 30),
      sendTimeout: const Duration(seconds: 30),
    ));

// The iOS OAuth client id used for the mobile PKCE auth-code flow (D23).
// Supply at build time:
//   --dart-define=GOOGLE_IOS_CLIENT_ID=<ios client id>
const _iosClientId =
    String.fromEnvironment('GOOGLE_IOS_CLIENT_ID', defaultValue: '');

// The WEB OAuth client id for the browser flow (spec 2026-07-18); same GCP
// client the backend exchanges with. --dart-define=GOOGLE_WEB_CLIENT_ID=...
const _webClientId =
    String.fromEnvironment('GOOGLE_WEB_CLIENT_ID', defaultValue: '');

// Ad prototype gate (spec 2026-07-17). Off unless the build passes
// --dart-define=SHOW_ADS=true. Kept in core (not lib/ads) so nothing outside
// lib/ads/ imports the ad SDK. Wrapped in a provider so widget tests can flip it.
const kShowAds = bool.fromEnvironment('SHOW_ADS', defaultValue: false);

final adsEnabledProvider = Provider<bool>((ref) => kShowAds);

final tokenStoreProvider =
    Provider<TokenStore>((ref) => TokenStore(const FlutterSecureStorage()));

final apiClientProvider = Provider<ApiClient>((ref) {
  final store = ref.watch(tokenStoreProvider);
  return ApiClient(
    buildDio(),
    jwtProvider: store.readJwt,
    // Expired/invalid JWT (401) -> clear the session; the auth gate then shows
    // sign-in. ref.read at call time avoids a build-time provider cycle.
    onUnauthorized: () =>
        ref.read(sessionProvider.notifier).handleUnauthorized(),
  );
});

final googleAuthCodesProvider = Provider<GoogleAuthCodes>(
  (ref) => kIsWeb
      ? BrowserPkceCodes(webClientId: _webClientId, origin: Uri.base.origin)
      : WebAuthPkceCodes(iosClientId: _iosClientId),
);

final authServiceProvider = Provider<AuthService>((ref) => AuthService(
      ref.watch(apiClientProvider),
      ref.watch(tokenStoreProvider),
      ref.watch(googleAuthCodesProvider),
      exchangePath:
          kIsWeb ? '/api/v1/auth/google/web' : '/api/v1/auth/google/mobile',
    ));

// FCM reminder push (D22/D27). start() is triggered by the signed-in shell.
final pushServiceProvider = Provider<PushService>(
  (ref) => PushService(DeviceRegistrar(ref.watch(apiClientProvider))),
);
