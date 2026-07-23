import 'package:flutter/services.dart' show PlatformException;
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_web_auth_2/flutter_web_auth_2.dart';
import 'package:mamaflow/auth/google_auth_codes.dart';

const _clientId = '12345-abcdef.apps.googleusercontent.com';

void main() {
  test('builds a PKCE auth URL with state and returns the echoed code',
      () async {
    late Uri authUri;
    Future<String> fake({
      required String url,
      required String callbackUrlScheme,
      required FlutterWebAuth2Options options,
    }) async {
      authUri = Uri.parse(url);
      final state = authUri.queryParameters['state'];
      return '$callbackUrlScheme:/oauth2redirect?code=C123&state=$state';
    }

    final codes = WebAuthPkceCodes(iosClientId: _clientId, authenticate: fake);
    final result = await codes.obtainAuthorizationCode();

    expect(result!.code, 'C123');
    expect(result.codeVerifier, isNotEmpty);
    expect(authUri.queryParameters['code_challenge'], isNotEmpty);
    expect(authUri.queryParameters['code_challenge_method'], 'S256');
    expect(authUri.queryParameters['state'], isNotEmpty);
  });

  test('returns null (not an error) when the user cancels the sheet',
      () async {
    Future<String> fake({
      required String url,
      required String callbackUrlScheme,
      required FlutterWebAuth2Options options,
    }) async {
      throw PlatformException(code: 'CANCELED');
    }

    final codes = WebAuthPkceCodes(iosClientId: _clientId, authenticate: fake);

    expect(await codes.obtainAuthorizationCode(), isNull);
  });

  test('rejects a callback whose state does not match (RFC 8252)', () async {
    Future<String> fake({
      required String url,
      required String callbackUrlScheme,
      required FlutterWebAuth2Options options,
    }) async =>
        '$callbackUrlScheme:/oauth2redirect?code=C123&state=attacker-forged';

    final codes = WebAuthPkceCodes(iosClientId: _clientId, authenticate: fake);

    await expectLater(codes.obtainAuthorizationCode(), throwsStateError);
  });

  test('fails loudly when the client id dart-define is missing', () async {
    final codes = WebAuthPkceCodes(iosClientId: '');

    await expectLater(codes.obtainAuthorizationCode(), throwsStateError);
  });

  group('BrowserPkceCodes', () {
    test('builds the auth URL against the web client and origin redirect', () async {
      String? capturedUrl;
      Future<String> fake({
        required String url,
        required String callbackUrlScheme,
        required FlutterWebAuth2Options options,
      }) async {
        capturedUrl = url;
        final state = Uri.parse(url).queryParameters['state']!;
        return 'https://app.mamaflow.example/auth.html?code=C1&state=$state';
      }

      final codes = BrowserPkceCodes(
        webClientId: 'web-id.apps.googleusercontent.com',
        origin: 'https://app.mamaflow.example',
        authenticate: fake,
      );

      final result = await codes.obtainAuthorizationCode();

      final q = Uri.parse(capturedUrl!).queryParameters;
      expect(q['client_id'], 'web-id.apps.googleusercontent.com');
      expect(q['redirect_uri'], 'https://app.mamaflow.example/auth.html');
      expect(q['code_challenge_method'], 'S256');
      expect(result!.code, 'C1');
    });

    test('empty web client id fails loudly', () {
      final codes = BrowserPkceCodes(webClientId: '', origin: 'https://x');
      expect(codes.obtainAuthorizationCode, throwsStateError);
    });

    test('state mismatch drops the code', () async {
      Future<String> fake({
        required String url,
        required String callbackUrlScheme,
        required FlutterWebAuth2Options options,
      }) async =>
          'https://app.mamaflow.example/auth.html?code=C1&state=WRONG';
      final codes = BrowserPkceCodes(
          webClientId: 'id', origin: 'https://app.mamaflow.example', authenticate: fake);
      expect(codes.obtainAuthorizationCode, throwsStateError);
    });
  });
}
