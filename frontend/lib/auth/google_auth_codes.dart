import 'package:google_sign_in/google_sign_in.dart';

/// Boundary around the Google sign-in plugin: obtain a one-time **serverAuthCode**
/// for the backend to exchange for Gmail tokens (D23 — those tokens never touch
/// the device, D4). Kept as an interface so AuthService is testable without the
/// plugin / a device.
abstract class GoogleAuthCodes {
  /// Runs Google authentication + server authorization and returns a
  /// serverAuthCode, or null if the user denied the Gmail authorization.
  /// Throws [GoogleSignInException] on cancellation / failure.
  Future<String?> obtainServerAuthCode();

  Future<void> signOut();
}

/// Real implementation backed by google_sign_in 7.x.
class GoogleSignInAuthCodes implements GoogleAuthCodes {
  GoogleSignInAuthCodes(this._google, {required String serverClientId})
      // ignore: prefer_initializing_formals — public named param maps to a private field
      : _serverClientId = serverClientId;

  final GoogleSignIn _google;
  final String _serverClientId;
  bool _initialized = false;

  // Read-only Gmail — the only scope the extraction pipeline needs.
  static const _scopes = <String>['https://www.googleapis.com/auth/gmail.readonly'];

  Future<void> _ensureInitialized() async {
    if (_initialized) return;
    // serverClientId = the WEB OAuth client id; the backend exchanges the code
    // with the matching web client secret.
    await _google.initialize(serverClientId: _serverClientId);
    _initialized = true;
  }

  @override
  Future<String?> obtainServerAuthCode() async {
    await _ensureInitialized();
    await _google.authenticate(scopeHint: const <String>['email']);
    final authorization = await _google.authorizationClient.authorizeServer(_scopes);
    return authorization?.serverAuthCode;
  }

  @override
  Future<void> signOut() => _google.signOut();
}
