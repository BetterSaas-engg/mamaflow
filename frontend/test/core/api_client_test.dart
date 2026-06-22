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
}
