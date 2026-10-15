import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/outils/saisie_rapide.dart';

// Wednesday 14 October 2026, 09:00.
final ref = DateTime(2026, 10, 14, 9);
ResultatDeSaisie a(String s) => analyserLaSaisie(s, maintenant: ref);

void main() {
  group('French', () {
    test('title, tomorrow, time and place', () {
      final r = a('Déjeuner avec Camille demain 12h30 au Café du Marché');
      expect(r.titre, 'Déjeuner avec Camille');
      expect(r.debut, DateTime(2026, 10, 15, 12, 30));
      expect(r.fin, DateTime(2026, 10, 15, 13, 30));
      expect(r.lieu, 'Café du Marché');
    });
    test('weekday and a time range', () {
      final r = a('Revue de sprint vendredi 14h-15h30');
      expect(r.titre, 'Revue de sprint');
      expect(r.debut, DateTime(2026, 10, 16, 14));
      expect(r.fin, DateTime(2026, 10, 16, 15, 30));
    });
    test('explicit date and a duration', () {
      final r = a('Atelier le 3 novembre à 9h pendant 2h');
      expect(r.titre, 'Atelier');
      expect(r.debut, DateTime(2026, 11, 3, 9));
      expect(r.fin, DateTime(2026, 11, 3, 11));
    });
    test('a date without a time is all day', () {
      final r = a('Congé 23/12');
      expect(r.titre, 'Congé');
      expect(r.journeeEntiere, isTrue);
      expect(r.debut, DateTime(2026, 12, 23));
    });
    test('midi', () {
      expect(a('Déjeuner demain midi').debut, DateTime(2026, 10, 15, 12));
    });
    test('the same weekday means next week', () {
      expect(a('Point mercredi 10h').debut, DateTime(2026, 10, 21, 10));
    });
  });

  group('English', () {
    test('weekday, pm and a duration', () {
      final r = a('Call with Sam friday 2pm for 1h');
      expect(r.titre, 'Call with Sam');
      expect(r.debut, DateTime(2026, 10, 16, 14));
      expect(r.fin, DateTime(2026, 10, 16, 15));
    });
    test('month name first, place', () {
      final r = a('Dentist Oct 20 at 4:30pm at City Clinic');
      expect(r.titre, 'Dentist');
      expect(r.debut, DateTime(2026, 10, 20, 16, 30));
      expect(r.lieu, 'City Clinic');
    });
    test('minutes', () {
      final r = a('Standup tomorrow 9:15am 15 min');
      expect(r.debut, DateTime(2026, 10, 15, 9, 15));
      expect(r.fin, DateTime(2026, 10, 15, 9, 30));
    });
  });

  test('a past time with no date moves to tomorrow', () {
    expect(a('Appel 8h').debut, DateTime(2026, 10, 15, 8));
  });
  test('plain text stays a title', () {
    final r = a('Idée de cadeau');
    expect(r.titre, 'Idée de cadeau');
    expect(r.debut, isNull);
  });
  test('a past date without a year means next year', () {
    expect(a('Anniversaire 5 mars').debut, DateTime(2027, 3, 5));
  });
}
