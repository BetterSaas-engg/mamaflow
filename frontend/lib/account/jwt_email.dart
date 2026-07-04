import 'dart:convert';

/// Returns the `email` claim from a JWT's payload segment, or null if the
/// token is absent, malformed, or has no email. Pure — no verification (the
/// server issued and signs the token; this only reads a claim for display).
String? emailFromJwt(String? jwt) {
  if (jwt == null) return null;
  final parts = jwt.split('.');
  if (parts.length != 3) return null;
  try {
    final payload = utf8.decode(base64Url.decode(base64Url.normalize(parts[1])));
    final map = jsonDecode(payload);
    if (map is Map && map['email'] is String) return map['email'] as String;
    return null;
  } catch (_) {
    return null;
  }
}
