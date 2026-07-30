import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/auth/google_auth_codes.dart';
import 'package:mamaflow/auth/pending_oauth.dart';

/// Recovery of a sign-in that Android interrupted by killing our process while
/// the user was on Google's consent screen (D43).
///
/// Reproduced on a real S25 Ultra: the redirect cold-starts the app, but the
/// Dart future awaiting it died with the old process. flutter_web_auth_2's
/// CallbackActivity hands the URL to a STATIC map — empty in the new process —
/// so the auth code was silently dropped and the user was dumped back at the
/// sign-in screen having just successfully consented.
void main() {
  const scheme = 'com.googleusercontent.apps.test-client';

  test('completes the sign-in when the redirect cold-starts the app', () async {
    final store = InMemoryPendingOAuthStore();
    await store.save(const PendingOAuth(verifier: 'v-123', state: 's-abc'));

    final result = await recoverPendingAuthorization(
      pendingStore: store,
      readInitialLink: () async =>
          Uri.parse('$scheme:/oauth2redirect?code=CODE9&state=s-abc'),
    );

    expect(result, isNotNull);
    expect(result!.code, 'CODE9');
    // The verifier is the half that cannot be reconstructed — without it the
    // code is worthless, which is exactly what used to happen.
    expect(result.codeVerifier, 'v-123');
  });

  test('consumes the pending record so a code cannot be replayed', () async {
    final store = InMemoryPendingOAuthStore();
    await store.save(const PendingOAuth(verifier: 'v-123', state: 's-abc'));
    final link = Uri.parse('$scheme:/oauth2redirect?code=CODE9&state=s-abc');

    await recoverPendingAuthorization(
        pendingStore: store, readInitialLink: () async => link);
    final second = await recoverPendingAuthorization(
        pendingStore: store, readInitialLink: () async => link);

    expect(await store.read(), isNull);
    expect(second, isNull);
  });

  test('rejects a redirect whose state does not match (RFC 8252)', () async {
    final store = InMemoryPendingOAuthStore();
    await store.save(const PendingOAuth(verifier: 'v-123', state: 's-abc'));

    final result = await recoverPendingAuthorization(
      pendingStore: store,
      readInitialLink: () async => Uri.parse('$scheme:/oauth2redirect?code=EVIL&state=other'),
    );

    // Persisting the verifier must not weaken the callback-binding check.
    expect(result, isNull);
    expect(await store.read(), isNull, reason: 'stale record left replayable');
  });

  test('a normal launch recovers nothing', () async {
    final store = InMemoryPendingOAuthStore();

    final result = await recoverPendingAuthorization(
      pendingStore: store,
      readInitialLink: () async => Uri.parse('$scheme:/oauth2redirect?code=CODE9&state=s'),
    );

    expect(result, isNull);
  });

  test('an abandoned sign-in is dropped rather than left pending', () async {
    // Started consent, never finished, later opens the app normally. The stale
    // record must not linger to be matched against some future callback.
    final store = InMemoryPendingOAuthStore();
    await store.save(const PendingOAuth(verifier: 'v-123', state: 's-abc'));

    final result = await recoverPendingAuthorization(
      pendingStore: store,
      readInitialLink: () async => null,
    );

    expect(result, isNull);
    expect(await store.read(), isNull);
  });

  test('a redirect carrying an error instead of a code recovers nothing',
      () async {
    final store = InMemoryPendingOAuthStore();
    await store.save(const PendingOAuth(verifier: 'v-123', state: 's-abc'));

    final result = await recoverPendingAuthorization(
      pendingStore: store,
      readInitialLink: () async =>
          Uri.parse('$scheme:/oauth2redirect?error=access_denied&state=s-abc'),
    );

    expect(result, isNull);
    expect(await store.read(), isNull);
  });

  group('PendingOAuth store', () {
    test('corrupt data reads as nothing pending, never an exception', () async {
      // A half-written record must not wedge sign-in forever.
      final pending = PendingOAuth.fromJson({'verifier': 'v'});
      expect(pending, isNull);
      expect(PendingOAuth.fromJson({'verifier': '', 'state': 's'}), isNull);
      expect(PendingOAuth.fromJson({'verifier': 'v', 'state': 1}), isNull);
    });
  });
}
