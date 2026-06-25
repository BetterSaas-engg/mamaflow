import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'auth/session_controller.dart';
import 'ui/home_screen.dart';
import 'ui/sign_in_screen.dart';

final _router = GoRouter(
  routes: [
    GoRoute(path: '/', builder: (context, state) => const AuthGate()),
  ],
);

class MamaflowApp extends StatelessWidget {
  const MamaflowApp({super.key});

  @override
  Widget build(BuildContext context) {
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
      data: (signedIn) => signedIn ? const HomeScreen() : const SignInScreen(),
      loading: () => const Scaffold(body: Center(child: CircularProgressIndicator())),
      // A failed hydrate (e.g. no secure storage yet) means "not signed in".
      error: (_, _) => const SignInScreen(),
    );
  }
}
