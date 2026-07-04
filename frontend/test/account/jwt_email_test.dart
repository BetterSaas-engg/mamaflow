import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/account/jwt_email.dart';

String _jwt(Map<String, dynamic> payload) {
  String seg(Map<String, dynamic> m) =>
      base64Url.encode(utf8.encode(jsonEncode(m))).replaceAll('=', '');
  return '${seg({'alg': 'HS256'})}.${seg(payload)}.sig';
}

void main() {
  test('extracts the email claim from a JWT payload', () {
    expect(emailFromJwt(_jwt({'sub': '1', 'email': 'a@b.com'})), 'a@b.com');
  });

  test('returns null for a payload without email', () {
    expect(emailFromJwt(_jwt({'sub': '1'})), isNull);
  });

  test('returns null for malformed or null input', () {
    expect(emailFromJwt(null), isNull);
    expect(emailFromJwt('not-a-jwt'), isNull);
    expect(emailFromJwt('a.b'), isNull);
    expect(emailFromJwt('a.!!!.c'), isNull);
  });
}
