import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';
import 'account_service.dart';
import 'jwt_email.dart';

/// The signed-in account's email, read from the stored session JWT. Null if
/// no token or no email claim.
final accountEmailProvider = FutureProvider<String?>((ref) async {
  final jwt = await ref.watch(tokenStoreProvider).readJwt();
  return emailFromJwt(jwt);
});

final accountServiceProvider =
    Provider<AccountService>((ref) => AccountService(ref.watch(apiClientProvider)));
