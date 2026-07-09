import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../auth/auth_service.dart';
import '../auth/google_auth_codes.dart';
import '../auth/session_controller.dart';
import '../auth/token_store.dart';
import '../push/device_registrar.dart';
import '../push/push_service.dart';
import 'api_client.dart';

const _baseUrl =
    String.fromEnvironment('API_BASE_URL', defaultValue: 'http://localhost:8000');

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
    Dio(BaseOptions(baseUrl: _baseUrl)),
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
