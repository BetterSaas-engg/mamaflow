import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/auth/auth_service.dart';
import 'package:mamaflow/auth/session_controller.dart';
import 'package:mamaflow/core/providers.dart';
import 'package:mamaflow/push/push_service.dart';
import 'package:mocktail/mocktail.dart';

class _MockAuth extends Mock implements AuthService {}

class _MockPush extends Mock implements PushService {}

void main() {
  late _MockAuth auth;
  late _MockPush push;
  late ProviderContainer container;

  setUp(() {
    auth = _MockAuth();
    push = _MockPush();
    when(() => auth.isSignedIn()).thenAnswer((_) async => true);
    when(() => auth.signOut()).thenAnswer((_) async {});
    when(() => push.stop()).thenAnswer((_) async {});
    when(() => push.stop(unregisterFromBackend: false))
        .thenAnswer((_) async {});
    container = ProviderContainer(overrides: [
      authServiceProvider.overrideWithValue(auth),
      pushServiceProvider.overrideWithValue(push),
    ]);
    addTearDown(container.dispose);
  });

  test('signOut unregisters push (backend included) before clearing the JWT',
      () async {
    await container.read(sessionProvider.future);

    await container.read(sessionProvider.notifier).signOut();

    verifyInOrder([
      () => push.stop(),
      () => auth.signOut(),
    ]);
    expect(container.read(sessionProvider).value, false);
  });

  test('a cancelled sign-in leaves the session signed out', () async {
    when(() => auth.isSignedIn()).thenAnswer((_) async => false);
    when(() => auth.signInWithGoogle()).thenAnswer((_) async => null);
    await container.read(sessionProvider.future);

    final user = await container.read(sessionProvider.notifier).signIn();

    expect(user, isNull);
    expect(container.read(sessionProvider).value, false);
  });

  test('handleUnauthorized resets push locally without a backend call',
      () async {
    await container.read(sessionProvider.future);

    await container.read(sessionProvider.notifier).handleUnauthorized();

    // The JWT is already invalid: an authed unregister would 401 and re-fire
    // this handler. Local reset only; the row is reclaimed on next sign-in.
    verify(() => push.stop(unregisterFromBackend: false)).called(1);
    verifyNever(() => push.stop());
    verify(() => auth.signOut()).called(1);
    expect(container.read(sessionProvider).value, false);
  });
}
