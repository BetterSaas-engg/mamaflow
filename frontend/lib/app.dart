import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'auth/session_controller.dart';
import 'ui/home_shell.dart';
import 'ui/sign_in_screen.dart';

final rootNavigatorKey = GlobalKey<NavigatorState>();

final _router = GoRouter(
  navigatorKey: rootNavigatorKey,
  routes: [
    GoRoute(path: '/', builder: (context, state) => const AuthGate()),
  ],
);

class MamaflowApp extends ConsumerWidget {
  const MamaflowApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // A session flip to signed-out (sign-out, account deletion, or a 401
    // auto-signout) must also clear any pushed routes — AuthGate only swaps
    // the base route, so a stale Settings/detail screen (showing account or
    // item content) would otherwise stay stacked above the sign-in screen.
    ref.listen(sessionProvider, (previous, next) {
      final wasSignedIn = previous?.value ?? false;
      final isSignedIn = next.value ?? false;
      if (wasSignedIn && !isSignedIn) {
        rootNavigatorKey.currentState?.popUntil((route) => route.isFirst);
      }
    });
    return MaterialApp.router(
      title: 'Mamaflow',
      routerConfig: _router,
    );
  }
}

/// Routes between the sign-in screen and the home screen based on the session
/// state (hydrated from the token store at startup).
class AuthGate extends ConsumerWidget {
  const AuthGate({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(sessionProvider);
    return session.when(
      data: (signedIn) => signedIn ? const HomeShell() : const SignInScreen(),
      loading: () => const Scaffold(body: Center(child: CircularProgressIndicator())),
      // A failed hydrate (e.g. no secure storage yet) means "not signed in".
      error: (_, _) => const SignInScreen(),
    );
  }
}
