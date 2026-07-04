import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../auth/session_controller.dart';
import '../core/providers.dart';
import 'account_service.dart';
import 'jwt_email.dart';

/// The signed-in account's email, read from the stored session JWT. Null if
/// no token or no email claim.
final accountEmailProvider = FutureProvider<String?>((ref) async {
  // Recompute when auth state flips (sign-out / sign-in as a different
  // account) so a stale email from a prior session can't linger.
  ref.watch(sessionProvider);
  final jwt = await ref.watch(tokenStoreProvider).readJwt();
  return emailFromJwt(jwt);
});

final accountServiceProvider =
    Provider<AccountService>((ref) => AccountService(ref.watch(apiClientProvider)));
