import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/auth/auth_service.dart';
import 'package:mamaflow/auth/google_auth_codes.dart';
import 'package:mamaflow/auth/token_store.dart';
import 'package:mamaflow/core/api_client.dart';
import 'package:mocktail/mocktail.dart';

class _MockApi extends Mock implements ApiClient {}

class _MockTokenStore extends Mock implements TokenStore {}

/// A controllable stand-in for the Google sign-in plugin boundary so the
/// exchange logic is testable without the real plugin / a device.
class _FakeGoogle implements GoogleAuthCodes {
  _FakeGoogle(this.code);
  final String? code;
  bool signedOut = false;

  @override
  Future<String?> obtainServerAuthCode() async => code;

  @override
  Future<void> signOut() async => signedOut = true;
}

void main() {
  setUpAll(() => registerFallbackValue(<String, dynamic>{}));

  test('exchanges serverAuthCode for a JWT, stores it, returns the user', () async {
    final api = _MockApi();
    final store = _MockTokenStore();
    when(() => api.postJson(any(), any())).thenAnswer((_) async => {
          'access_token': 'JWT123',
          'token_type': 'bearer',
          'expires_in': 900,
          'user': {'id': 'u1', 'email': 'parent@example.com'},
        });
    when(() => store.saveJwt(any())).thenAnswer((_) async {});
    final auth = AuthService(api, store, _FakeGoogle('CODE'));

    final user = await auth.signInWithGoogle();

    expect(user.id, 'u1');
    expect(user.email, 'parent@example.com');
    final captured = verify(() => api.postJson(captureAny(), captureAny())).captured;
    expect(captured[0], '/api/v1/auth/google/mobile');
    expect(captured[1], {'server_auth_code': 'CODE'});
    verify(() => store.saveJwt('JWT123')).called(1);
  });

  test('throws and never calls the backend when sign-in is cancelled', () async {
    final api = _MockApi();
    final store = _MockTokenStore();
    final auth = AuthService(api, store, _FakeGoogle(null));

    await expectLater(auth.signInWithGoogle(), throwsA(isA<AuthException>()));
    verifyNever(() => api.postJson(any(), any()));
  });

  test('throws when the backend returns no access_token', () async {
    final api = _MockApi();
    final store = _MockTokenStore();
    when(() => api.postJson(any(), any())).thenAnswer((_) async => {'user': {}});
    final auth = AuthService(api, store, _FakeGoogle('CODE'));

    await expectLater(auth.signInWithGoogle(), throwsA(isA<AuthException>()));
    verifyNever(() => store.saveJwt(any()));
  });

  test('signOut clears the JWT and the Google session', () async {
    final api = _MockApi();
    final store = _MockTokenStore();
    when(() => store.clear()).thenAnswer((_) async {});
    final google = _FakeGoogle('x');
    final auth = AuthService(api, store, google);

    await auth.signOut();

    verify(() => store.clear()).called(1);
    expect(google.signedOut, true);
  });

  test('isSignedIn reflects whether a JWT is stored', () async {
    final api = _MockApi();
    final store = _MockTokenStore();
    when(() => store.readJwt()).thenAnswer((_) async => 'JWT');
    final auth = AuthService(api, store, _FakeGoogle('x'));

    expect(await auth.isSignedIn(), true);
  });
}
