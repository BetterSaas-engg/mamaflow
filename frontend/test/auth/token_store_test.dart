import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/auth/token_store.dart';
import 'package:mocktail/mocktail.dart';

class _MockStorage extends Mock implements FlutterSecureStorage {}

void main() {
  test('saves, reads, and clears the session jwt', () async {
    final storage = _MockStorage();
    final mem = <String, String>{};

    when(() => storage.write(key: any(named: 'key'), value: any(named: 'value')))
        .thenAnswer((inv) async {
      final k = inv.namedArguments[#key] as String;
      final v = inv.namedArguments[#value] as String?;
      if (v == null) {
        mem.remove(k);
      } else {
        mem[k] = v;
      }
    });
    when(() => storage.read(key: any(named: 'key')))
        .thenAnswer((inv) async => mem[inv.namedArguments[#key] as String]);
    when(() => storage.delete(key: any(named: 'key')))
        .thenAnswer((inv) async => mem.remove(inv.namedArguments[#key] as String));

    final store = TokenStore(storage);

    expect(await store.readJwt(), isNull);
    await store.saveJwt('JWT123');
    expect(await store.readJwt(), 'JWT123');
    await store.clear();
    expect(await store.readJwt(), isNull);
  });
}
