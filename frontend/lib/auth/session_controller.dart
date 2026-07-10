import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';
import 'auth_service.dart';

/// App session state: whether a JWT is present. Hydrated from the token store
/// at startup; flipped by sign-in / sign-out. The auth gate watches this.
class SessionController extends AsyncNotifier<bool> {
  @override
  Future<bool> build() => ref.read(authServiceProvider).isSignedIn();

  Future<AuthUser> signIn() async {
    final user = await ref.read(authServiceProvider).signInWithGoogle();
    state = const AsyncData(true);
    return user;
  }

  Future<void> signOut() async {
    // Unregister push first — the call needs the JWT that signOut() clears.
    await ref.read(pushServiceProvider).stop();
    await ref.read(authServiceProvider).signOut();
    state = const AsyncData(false);
  }

  /// Called by the API client on a 401 (expired/invalid JWT): clear the stored
  /// session and drop back to the sign-in screen. Push state resets locally
  /// only — an authed unregister would 401 and re-fire this handler; the next
  /// sign-in re-registers the device to whichever account it belongs to.
  Future<void> handleUnauthorized() async {
    await ref.read(pushServiceProvider).stop(unregisterFromBackend: false);
    await ref.read(authServiceProvider).signOut();
    state = const AsyncData(false);
  }
}

final sessionProvider =
    AsyncNotifierProvider<SessionController, bool>(SessionController.new);
