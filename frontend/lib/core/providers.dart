import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:google_sign_in/google_sign_in.dart';

import '../auth/auth_service.dart';
import '../auth/google_auth_codes.dart';
import '../auth/token_store.dart';
import 'api_client.dart';

const _baseUrl =
    String.fromEnvironment('API_BASE_URL', defaultValue: 'http://localhost:8000');

// The WEB OAuth client id (the backend exchanges the serverAuthCode with the
// matching web client secret). Supply at build time:
//   --dart-define=GOOGLE_SERVER_CLIENT_ID=<web client id>
const _serverClientId =
    String.fromEnvironment('GOOGLE_SERVER_CLIENT_ID', defaultValue: '');

final tokenStoreProvider =
    Provider<TokenStore>((ref) => TokenStore(const FlutterSecureStorage()));

final apiClientProvider = Provider<ApiClient>((ref) {
  final store = ref.watch(tokenStoreProvider);
  return ApiClient(Dio(BaseOptions(baseUrl: _baseUrl)), jwtProvider: store.readJwt);
});

final googleAuthCodesProvider = Provider<GoogleAuthCodes>(
  (ref) => GoogleSignInAuthCodes(GoogleSignIn.instance, serverClientId: _serverClientId),
);

final authServiceProvider = Provider<AuthService>((ref) => AuthService(
      ref.watch(apiClientProvider),
      ref.watch(tokenStoreProvider),
      ref.watch(googleAuthCodesProvider),
    ));
