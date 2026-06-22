import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Stores ONLY the app's own session JWT (D4: Gmail/OAuth tokens stay
/// server-side, never on the device). Backed by the platform secure store.
class TokenStore {
  static const _key = 'mamaflow_session_jwt';
  final FlutterSecureStorage _storage;

  TokenStore(this._storage);

  Future<void> saveJwt(String jwt) => _storage.write(key: _key, value: jwt);
  Future<String?> readJwt() => _storage.read(key: _key);
  Future<void> clear() => _storage.delete(key: _key);
}
