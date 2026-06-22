import 'package:dio/dio.dart';

/// Thin REST/JSON client to the Mamaflow API. Attaches the app session JWT
/// (when present) as a Bearer token on every request. Gmail/OAuth tokens never
/// live on the device (D4) — only the app's own session JWT, supplied here.
class ApiClient {
  final Dio _dio;
  final Future<String?> Function() _jwtProvider;

  ApiClient(this._dio, {required Future<String?> Function() jwtProvider})
      // ignore: prefer_initializing_formals — public named param maps to a private field
      : _jwtProvider = jwtProvider {
    _dio.interceptors.add(InterceptorsWrapper(onRequest: (options, handler) async {
      final jwt = await _jwtProvider();
      if (jwt != null && jwt.isNotEmpty) {
        options.headers['Authorization'] = 'Bearer $jwt';
      }
      handler.next(options);
    }));
  }

  Future<Map<String, dynamic>> getJson(String path, {Map<String, dynamic>? query}) async {
    final r = await _dio.get(path, queryParameters: query);
    return Map<String, dynamic>.from(r.data as Map);
  }

  Future<Map<String, dynamic>> postJson(String path, Map<String, dynamic> body) async {
    final r = await _dio.post(path, data: body);
    return Map<String, dynamic>.from(r.data as Map);
  }
}
