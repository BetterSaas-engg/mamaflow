import 'package:dio/dio.dart';

/// Thin REST/JSON client to the Mamaflow API. Attaches the app session JWT
/// (when present) as a Bearer token on every request. Gmail/OAuth tokens never
/// live on the device (D4) — only the app's own session JWT, supplied here.
///
/// onUnauthorized fires on any 401 (expired/invalid session JWT) so the app can
/// clear the session and return to sign-in; the error still propagates.
class ApiClient {
  final Dio _dio;
  final Future<String?> Function() _jwtProvider;

  ApiClient(
    this._dio, {
    required Future<String?> Function() jwtProvider,
    Future<void> Function()? onUnauthorized,
  })
      // ignore: prefer_initializing_formals — public named param maps to a private field
      : _jwtProvider = jwtProvider {
    _dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) async {
        final jwt = await _jwtProvider();
        if (jwt != null && jwt.isNotEmpty) {
          options.headers['Authorization'] = 'Bearer $jwt';
        }
        handler.next(options);
      },
      onError: (e, handler) async {
        if (e.response?.statusCode == 401 && onUnauthorized != null) {
          await onUnauthorized();
        }
        handler.next(e);
      },
    ));
  }

  Future<Map<String, dynamic>> getJson(String path, {Map<String, dynamic>? query}) async {
    final r = await _dio.get(path, queryParameters: query);
    return Map<String, dynamic>.from(r.data as Map);
  }

  Future<Map<String, dynamic>> postJson(String path, Map<String, dynamic> body) async {
    final r = await _dio.post(path, data: body);
    return Map<String, dynamic>.from(r.data as Map);
  }

  /// POST whose response carries no JSON body (e.g. a 204).
  Future<void> postVoid(String path, Map<String, dynamic> body) async {
    await _dio.post(path, data: body);
  }

  Future<Map<String, dynamic>> patchJson(String path, Map<String, dynamic> body) async {
    final r = await _dio.patch(path, data: body);
    return Map<String, dynamic>.from(r.data as Map);
  }

  Future<void> delete(String path) async {
    await _dio.delete(path);
  }
}
