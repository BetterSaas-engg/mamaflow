import 'dart:convert';
import 'dart:math';

import 'package:crypto/crypto.dart';
import 'package:flutter_web_auth_2/flutter_web_auth_2.dart';

/// Result of the OAuth authorization step: the code to exchange plus the PKCE
/// verifier the backend needs to complete the exchange. (The redirect_uri is
/// derived server-side from the iOS client id — never client-supplied.)
class OAuthCodeResult {
  const OAuthCodeResult({required this.code, required this.codeVerifier});

  final String code;
  final String codeVerifier;
}

/// Boundary around the OAuth 2.0 authorization-code + PKCE flow (D23): opens
/// Google's consent in a secure web tab and returns an auth code for the backend
/// to exchange for Gmail tokens (which never touch the device, D4). Kept as an
/// interface so AuthService is testable without a device.
abstract class GoogleAuthCodes {
  /// Runs the consent flow and returns the code + PKCE verifier + redirect uri,
  /// or null if the user cancelled.
  Future<OAuthCodeResult?> obtainAuthorizationCode();

  Future<void> signOut();
}

/// Real implementation: OAuth 2.0 auth-code + PKCE via flutter_web_auth_2, using
/// the iOS OAuth client. google_sign_in can't mint a Gmail-scoped serverAuthCode
/// on iOS (see DECISIONS), so we run the flow directly.
class WebAuthPkceCodes implements GoogleAuthCodes {
  WebAuthPkceCodes({required String iosClientId}) : _clientId = iosClientId;

  final String _clientId;

  static const _scopes =
      'openid email https://www.googleapis.com/auth/gmail.readonly';

  /// iOS OAuth clients use the reversed client id as the redirect scheme
  /// (the same scheme registered in Info.plist).
  String get _redirectScheme {
    final prefix = _clientId.replaceAll('.apps.googleusercontent.com', '');
    return 'com.googleusercontent.apps.$prefix';
  }

  @override
  Future<OAuthCodeResult?> obtainAuthorizationCode() async {
    // Empty here => the build didn't get --dart-define=GOOGLE_IOS_CLIENT_ID
    // (e.g. launched from Xcode, which doesn't pass dart-defines). Fail loudly
    // instead of building a broken auth URL.
    if (_clientId.isEmpty) {
      throw StateError(
        'GOOGLE_IOS_CLIENT_ID is empty. Launch with: flutter run '
        '--dart-define=GOOGLE_IOS_CLIENT_ID=<ios client id> '
        "(Xcode's Run button does not pass --dart-define).",
      );
    }

    final verifier = _randomVerifier();
    final challenge = _s256Challenge(verifier);
    final redirectUri = '$_redirectScheme:/oauth2redirect';

    final url = Uri.https('accounts.google.com', '/o/oauth2/v2/auth', {
      'client_id': _clientId,
      'redirect_uri': redirectUri,
      'response_type': 'code',
      'scope': _scopes,
      'access_type': 'offline',
      'prompt': 'consent',
      'code_challenge': challenge,
      'code_challenge_method': 'S256',
    }).toString();

    // Ephemeral: no shared cookies, so the user re-picks their account each time
    // and we always get a fresh offline grant.
    final result = await FlutterWebAuth2.authenticate(
      url: url,
      callbackUrlScheme: _redirectScheme,
      options: const FlutterWebAuth2Options(preferEphemeral: true),
    );

    final code = Uri.parse(result).queryParameters['code'];
    if (code == null) return null;
    return OAuthCodeResult(code: code, codeVerifier: verifier);
  }

  @override
  Future<void> signOut() async {
    // The web-auth session is ephemeral; nothing persists to clear. The app's
    // own JWT is cleared by AuthService.
  }

  static String _randomVerifier() {
    const chars =
        'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~';
    final rand = Random.secure();
    return List.generate(64, (_) => chars[rand.nextInt(chars.length)]).join();
  }

  static String _s256Challenge(String verifier) {
    final digest = sha256.convert(ascii.encode(verifier));
    return base64UrlEncode(digest.bytes).replaceAll('=', '');
  }
}
