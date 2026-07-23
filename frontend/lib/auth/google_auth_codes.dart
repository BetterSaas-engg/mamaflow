import 'dart:convert';
import 'dart:math';

import 'package:crypto/crypto.dart';
import 'package:flutter/services.dart' show PlatformException;
import 'package:flutter_web_auth_2/flutter_web_auth_2.dart';

/// Matches FlutterWebAuth2.authenticate's shape; injectable so the flow is
/// testable without a device (the plugin API is a static method).
typedef WebAuthenticate = Future<String> Function({
  required String url,
  required String callbackUrlScheme,
  required FlutterWebAuth2Options options,
});

String _randomVerifier() {
  const chars =
      'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~';
  final rand = Random.secure();
  return List.generate(64, (_) => chars[rand.nextInt(chars.length)]).join();
}

String _s256Challenge(String verifier) {
  final digest = sha256.convert(ascii.encode(verifier));
  return base64UrlEncode(digest.bytes).replaceAll('=', '');
}

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
  WebAuthPkceCodes({required String iosClientId, WebAuthenticate? authenticate})
      : _clientId = iosClientId,
        _authenticate = authenticate ?? _pluginAuthenticate;

  final String _clientId;
  final WebAuthenticate _authenticate;

  static Future<String> _pluginAuthenticate({
    required String url,
    required String callbackUrlScheme,
    required FlutterWebAuth2Options options,
  }) =>
      FlutterWebAuth2.authenticate(
          url: url, callbackUrlScheme: callbackUrlScheme, options: options);

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
    // PKCE already binds the code to this app instance; `state` adds the
    // RFC 8252 §8.9 check that the callback belongs to THIS request.
    final state = _randomVerifier();

    final url = Uri.https('accounts.google.com', '/o/oauth2/v2/auth', {
      'client_id': _clientId,
      'redirect_uri': redirectUri,
      'response_type': 'code',
      'scope': _scopes,
      'access_type': 'offline',
      'prompt': 'consent',
      'code_challenge': challenge,
      'code_challenge_method': 'S256',
      'state': state,
    }).toString();

    final String result;
    try {
      // Ephemeral: no shared cookies, so the user re-picks their account each
      // time and we always get a fresh offline grant.
      result = await _authenticate(
        url: url,
        callbackUrlScheme: _redirectScheme,
        options: const FlutterWebAuth2Options(preferEphemeral: true),
      );
    } on PlatformException catch (e) {
      // Dismissing the consent sheet is a deliberate cancel, not an error.
      if (e.code == 'CANCELED') return null;
      rethrow;
    }

    final params = Uri.parse(result).queryParameters;
    if (params['state'] != state) {
      throw StateError('OAuth callback state mismatch — dropping the code.');
    }
    final code = params['code'];
    if (code == null) return null;
    return OAuthCodeResult(code: code, codeVerifier: verifier);
  }

  @override
  Future<void> signOut() async {
    // The web-auth session is ephemeral; nothing persists to clear. The app's
    // own JWT is cleared by AuthService.
  }
}

/// Browser (desktop web) implementation: the same OAuth 2.0 auth-code + PKCE
/// flow, but against the WEB OAuth client with an https redirect back to this
/// app origin's auth.html (which posts the callback URL to the opener —
/// flutter_web_auth_2's web contract). The backend exchanges the code with the
/// web client's secret; Gmail tokens never touch the browser (D4).
class BrowserPkceCodes implements GoogleAuthCodes {
  BrowserPkceCodes({
    required String webClientId,
    required String origin,
    WebAuthenticate? authenticate,
  })  : _clientId = webClientId,
        // The external param name (`origin`) must stay distinct from the
        // private field, so an initializing formal isn't an option here.
        // ignore: prefer_initializing_formals
        _origin = origin,
        _authenticate = authenticate ?? _pluginAuthenticate;

  final String _clientId;
  final String _origin;
  final WebAuthenticate _authenticate;

  static Future<String> _pluginAuthenticate({
    required String url,
    required String callbackUrlScheme,
    required FlutterWebAuth2Options options,
  }) =>
      FlutterWebAuth2.authenticate(
          url: url, callbackUrlScheme: callbackUrlScheme, options: options);

  static const _scopes =
      'openid email https://www.googleapis.com/auth/gmail.readonly';

  @override
  Future<OAuthCodeResult?> obtainAuthorizationCode() async {
    if (_clientId.isEmpty) {
      throw StateError(
        'GOOGLE_WEB_CLIENT_ID is empty. Build with: flutter build web '
        '--dart-define=GOOGLE_WEB_CLIENT_ID=<web client id>.',
      );
    }

    final verifier = _randomVerifier();
    final challenge = _s256Challenge(verifier);
    final redirectUri = '$_origin/auth.html';
    final state = _randomVerifier();

    final url = Uri.https('accounts.google.com', '/o/oauth2/v2/auth', {
      'client_id': _clientId,
      'redirect_uri': redirectUri,
      'response_type': 'code',
      'scope': _scopes,
      'access_type': 'offline',
      'prompt': 'consent',
      'code_challenge': challenge,
      'code_challenge_method': 'S256',
      'state': state,
    }).toString();

    final String result;
    try {
      result = await _authenticate(
        url: url,
        // On web the plugin matches the callback by the redirect page's
        // postMessage, not a custom scheme; 'https' is the documented value.
        callbackUrlScheme: 'https',
        options: const FlutterWebAuth2Options(),
      );
    } on PlatformException catch (e) {
      if (e.code == 'CANCELED') return null;
      rethrow;
    }

    final params = Uri.parse(result).queryParameters;
    if (params['state'] != state) {
      throw StateError('OAuth callback state mismatch — dropping the code.');
    }
    final code = params['code'];
    if (code == null) return null;
    return OAuthCodeResult(code: code, codeVerifier: verifier);
  }

  @override
  Future<void> signOut() async {}
}
