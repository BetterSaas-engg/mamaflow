import 'package:dio/dio.dart';

import '../core/api_client.dart';
import 'google_auth_codes.dart';
import 'token_store.dart';

/// The authenticated user the app knows about (identity only; Gmail tokens stay
/// server-side, D4).
class AuthUser {
  const AuthUser({required this.id, required this.email});
  final String id;
  final String email;
}

class AuthException implements Exception {
  const AuthException(this.message);
  final String message;
  @override
  String toString() => 'AuthException: $message';
}

/// Mobile sign-in (D23): Google serverAuthCode -> backend exchange
/// (POST /api/v1/auth/google/mobile) -> store the returned app session JWT.
class AuthService {
  AuthService(this._api, this._tokenStore, this._google,
      {String exchangePath = '/api/v1/auth/google/mobile'})
      // The external param name (`exchangePath`) must stay distinct from the
      // private field, so an initializing formal isn't an option here.
      // ignore: prefer_initializing_formals
      : _exchangePath = exchangePath;

  final ApiClient _api;
  final TokenStore _tokenStore;
  final GoogleAuthCodes _google;
  final String _exchangePath;

  /// Returns null when the user cancels the consent sheet — a deliberate act,
  /// not an error; callers must not surface it as a failure.
  Future<AuthUser?> signInWithGoogle() async {
    final result = await _google.obtainAuthorizationCode();
    if (result == null) return null;

    final resp = await _api.postJson(
      _exchangePath,
      {'code': result.code, 'code_verifier': result.codeVerifier},
    );

    final jwt = resp['access_token'] as String?;
    if (jwt == null || jwt.isEmpty) {
      throw const AuthException('Sign-in failed: no session token returned');
    }
    await _tokenStore.saveJwt(jwt);

    final user = (resp['user'] as Map?) ?? const {};
    return AuthUser(
      id: user['id'] as String? ?? '',
      email: user['email'] as String? ?? '',
    );
  }

  /// App-password (IMAP) sign-in: Yahoo/Rogers/iCloud. The backend verifies
  /// the credential with a real IMAP login and keeps it server-side (D4) —
  /// the password passes through this method's memory once and is never
  /// stored on the device.
  Future<AuthUser> signInWithAppPassword({
    required String provider,
    required String email,
    required String appPassword,
  }) async {
    Map<String, dynamic> resp;
    try {
      resp = await _api.postJson(
        '/api/v1/auth/imap',
        {'provider': provider, 'email': email, 'app_password': appPassword},
      );
    } on DioException catch (e) {
      // The backend's detail strings are written to be user-actionable
      // (wrong-app-password hint, throttle, provider down) — surface them.
      final detail = e.response?.data is Map
          ? (e.response!.data as Map)['detail']
          : null;
      throw AuthException(
        detail is String && detail.isNotEmpty
            ? detail
            : 'Sign-in failed. Please try again.',
      );
    }

    final jwt = resp['access_token'] as String?;
    if (jwt == null || jwt.isEmpty) {
      throw const AuthException('Sign-in failed: no session token returned');
    }
    await _tokenStore.saveJwt(jwt);

    final user = (resp['user'] as Map?) ?? const {};
    return AuthUser(
      id: user['id'] as String? ?? '',
      email: user['email'] as String? ?? '',
    );
  }

  Future<void> signOut() async {
    await _tokenStore.clear();
    try {
      await _google.signOut();
    } catch (_) {
      // The session JWT is already cleared; a failed Google sign-out
      // (e.g. not initialized) must not block local sign-out.
    }
  }

  Future<bool> isSignedIn() async {
    final jwt = await _tokenStore.readJwt();
    return jwt != null && jwt.isNotEmpty;
  }
}
