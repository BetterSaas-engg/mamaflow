import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart' show kReleaseMode;
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
Dio buildDio({String? baseUrl}) => Dio(BaseOptions(
      baseUrl: baseUrl ?? resolveBaseUrl(),
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 30),
      sendTimeout: const Duration(seconds: 30),
    ));

// The iOS OAuth client id used for the mobile PKCE auth-code flow (D23).
// Supply at build time:
//   --dart-define=GOOGLE_IOS_CLIENT_ID=<ios client id>
const _iosClientId =
    String.fromEnvironment('GOOGLE_IOS_CLIENT_ID', defaultValue: '');

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
  (ref) => WebAuthPkceCodes(iosClientId: _iosClientId),
);

final authServiceProvider = Provider<AuthService>((ref) => AuthService(
      ref.watch(apiClientProvider),
      ref.watch(tokenStoreProvider),
      ref.watch(googleAuthCodesProvider),
    ));

// FCM reminder push (D22/D27). start() is triggered by the signed-in shell.
final pushServiceProvider = Provider<PushService>(
  (ref) => PushService(DeviceRegistrar(ref.watch(apiClientProvider))),
);
