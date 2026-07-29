import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// The PKCE material for an in-flight Google sign-in, held somewhere that
/// survives the app process being killed.
///
/// Why this exists (D43): the verifier and `state` used to be local variables
/// inside `obtainAuthorizationCode`. While the user is on Google's consent
/// screen our app is backgrounded, and Android — Samsung especially, which
/// parks the app in the RARE standby bucket — is free to kill it. When that
/// happened, the local variables died with the process, so even a redirect
/// that came back perfectly had nothing left to exchange the code against.
class PendingOAuth {
  const PendingOAuth({required this.verifier, required this.state});

  final String verifier;
  final String state;

  Map<String, dynamic> toJson() => {'verifier': verifier, 'state': state};

  static PendingOAuth? fromJson(Map<String, dynamic> json) {
    final verifier = json['verifier'];
    final state = json['state'];
    if (verifier is! String || state is! String) return null;
    if (verifier.isEmpty || state.isEmpty) return null;
    return PendingOAuth(verifier: verifier, state: state);
  }
}

/// Where an in-flight sign-in is kept. An interface so tests (and any future
/// platform that lacks Keystore) can swap the backing store.
abstract class PendingOAuthStore {
  factory PendingOAuthStore({FlutterSecureStorage? storage}) =
      SecurePendingOAuthStore;

  Future<void> save(PendingOAuth pending);
  Future<PendingOAuth?> read();
  Future<void> clear();
}

/// Secure storage (Keystore-backed) rather than SharedPreferences: the
/// verifier is the secret half of PKCE, and a leaked one lets anyone who also
/// steals the redirect redeem the code.
class SecurePendingOAuthStore implements PendingOAuthStore {
  SecurePendingOAuthStore({FlutterSecureStorage? storage})
      : _storage = storage ?? const FlutterSecureStorage();

  final FlutterSecureStorage _storage;

  static const _key = 'pending_oauth';

  @override
  Future<void> save(PendingOAuth pending) =>
      _storage.write(key: _key, value: jsonEncode(pending.toJson()));

  /// The in-flight sign-in, or null if there isn't one. Corrupt data reads as
  /// "nothing pending" — a half-written record must never wedge sign-in.
  @override
  Future<PendingOAuth?> read() async {
    final raw = await _storage.read(key: _key);
    if (raw == null) return null;
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! Map<String, dynamic>) return null;
      return PendingOAuth.fromJson(decoded);
    } on FormatException {
      return null;
    }
  }

  @override
  Future<void> clear() => _storage.delete(key: _key);
}

/// In-memory store for tests and for the web build, which never uses the
/// deep-link redirect path.
class InMemoryPendingOAuthStore implements PendingOAuthStore {
  PendingOAuth? _value;

  @override
  Future<void> save(PendingOAuth pending) async => _value = pending;

  @override
  Future<PendingOAuth?> read() async => _value;

  @override
  Future<void> clear() async => _value = null;
}
