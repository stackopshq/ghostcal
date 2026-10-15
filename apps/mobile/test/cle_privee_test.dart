import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/services/auth.dart';

void main() {
  // A real X25519 PKCS#8 key as WebCrypto exports it.
  const pkcs8 = 'MC4CAQAwBQYDK2VuBCIEICgZYk9PD9l9b63sJ4+ZuQlqD8SbUtRE2L4SoXut2wFy';

  test('the web wraps raw PKCS#8 bytes: they come back as base64', () {
    expect(clePriveeDepuisEnveloppe(base64Decode(pkcs8)), pkcs8);
  });

  test('the bench tool wraps the base64 text: it is read as text', () {
    expect(clePriveeDepuisEnveloppe(utf8.encode(pkcs8)), pkcs8);
  });
}
