import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/core/providers.dart';

void main() {
  test('buildDio sets bounded timeouts (a dead network must not hang forever)',
      () {
    final dio = buildDio(baseUrl: 'https://api.test');
    expect(dio.options.connectTimeout, isNotNull);
    expect(dio.options.receiveTimeout, isNotNull);
    expect(dio.options.sendTimeout, isNotNull);
  });

  test('resolveBaseUrl falls back to localhost in debug builds', () {
    expect(resolveBaseUrl(defined: '', isRelease: false),
        'http://localhost:8000');
  });

  test('a release build without API_BASE_URL fails loudly', () {
    // Silently pointing a store build at localhost is a build mistake —
    // mirror the GOOGLE_IOS_CLIENT_ID fail-loud guard.
    expect(() => resolveBaseUrl(defined: '', isRelease: true),
        throwsStateError);
  });

  test('a release build rejects a non-https base URL', () {
    expect(
        () => resolveBaseUrl(defined: 'http://api.example.com', isRelease: true),
        throwsStateError);
  });

  test('a release build accepts an https base URL', () {
    expect(resolveBaseUrl(defined: 'https://api.example.com', isRelease: true),
        'https://api.example.com');
  });
}
