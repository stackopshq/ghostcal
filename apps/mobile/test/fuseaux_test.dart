import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/outils/fuseaux.dart';

void main() {
  test('a city finds its zone whatever the separators', () {
    expect(filtrerLesFuseaux('new york'), contains('America/New_York'));
    expect(filtrerLesFuseaux('zur'), ['Europe/Zurich']);
  });
  test('an empty search lists every common zone', () {
    expect(filtrerLesFuseaux('  '), fuseauxCourants);
  });
  test('every listed zone is an IANA-looking name', () {
    for (final f in fuseauxCourants) {
      expect(f == 'UTC' || f.contains('/'), isTrue, reason: f);
    }
  });
}
