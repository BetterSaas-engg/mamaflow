import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/core/api_client.dart';

/// Captures the outgoing request so we can assert on headers, and returns a
/// canned JSON body. Matches dio 5.x's HttpClientAdapter signature.
class _CapturingAdapter implements HttpClientAdapter {
  RequestOptions? last;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    last = options;
    return ResponseBody.fromString(
      '{"ok":true}',
      200,
      headers: {
        Headers.contentTypeHeader: [Headers.jsonContentType],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

void main() {
  test('attaches bearer token when jwt present', () async {
    final dio = Dio(BaseOptions(baseUrl: 'https://api.test'));
    final adapter = _CapturingAdapter();
    dio.httpClientAdapter = adapter;
    final client = ApiClient(dio, jwtProvider: () async => 'TESTJWT');

    final body = await client.getJson('/api/v1/items');

    expect(body['ok'], true);
    expect(adapter.last!.headers['Authorization'], 'Bearer TESTJWT');
  });

  test('omits auth header when no jwt', () async {
    final dio = Dio(BaseOptions(baseUrl: 'https://api.test'));
    final adapter = _CapturingAdapter();
    dio.httpClientAdapter = adapter;
    final client = ApiClient(dio, jwtProvider: () async => null);

    await client.getJson('/api/v1/items');

    expect(adapter.last!.headers.containsKey('Authorization'), false);
  });

  ApiClient clientWithStatus(int status, {Future<void> Function()? onUnauthorized}) {
    final dio = Dio(BaseOptions(baseUrl: 'https://api.test'))
      ..httpClientAdapter = _FixedStatusAdapter(status);
    return ApiClient(dio, jwtProvider: () async => 'jwt', onUnauthorized: onUnauthorized);
  }

  test('a 401 response triggers onUnauthorized and still throws', () async {
    var fired = 0;
    final api = clientWithStatus(401, onUnauthorized: () async => fired++);

    await expectLater(api.getJson('/api/v1/items'), throwsA(isA<DioException>()));
    expect(fired, 1);
  });

  test('non-401 errors do not trigger onUnauthorized', () async {
    var fired = 0;
    final api = clientWithStatus(500, onUnauthorized: () async => fired++);

    await expectLater(api.getJson('/api/v1/items'), throwsA(isA<DioException>()));
    expect(fired, 0);
  });
}

/// Fake transport returning a fixed status code — no network involved.
class _FixedStatusAdapter implements HttpClientAdapter {
  _FixedStatusAdapter(this.statusCode);
  final int statusCode;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async =>
      ResponseBody.fromString(
        '{"detail":"x"}',
        statusCode,
        headers: {
          Headers.contentTypeHeader: [Headers.jsonContentType],
        },
      );

  @override
  void close({bool force = false}) {}
}
