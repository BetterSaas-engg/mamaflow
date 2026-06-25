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
    await ref.read(authServiceProvider).signOut();
    state = const AsyncData(false);
  }
}

final sessionProvider =
    AsyncNotifierProvider<SessionController, bool>(SessionController.new);
