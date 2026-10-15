import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/outils/calendrier.dart';
import 'package:ghostcal/outils/couloirs.dart';

({DateTime debut, DateTime fin}) iv(int h1, int m1, int h2, int m2) =>
    (debut: DateTime(2026, 10, 14, h1, m1), fin: DateTime(2026, 10, 14, h2, m2));

void main() {
  group('repartirEnCouloirs (same cases as the web)', () {
    test('a lone event takes the full width', () {
      expect(repartirEnCouloirs([iv(9, 0, 10, 0)]), [(couloir: 0, couloirs: 1)]);
    });
    test('two simultaneous events sit side by side', () {
      expect(repartirEnCouloirs([iv(9, 0, 10, 0), iv(9, 0, 10, 0)]),
          [(couloir: 0, couloirs: 2), (couloir: 1, couloirs: 2)]);
    });
    test('touching events do not split', () {
      expect(repartirEnCouloirs([iv(9, 0, 10, 0), iv(10, 0, 11, 0)]),
          [(couloir: 0, couloirs: 1), (couloir: 0, couloirs: 1)]);
    });
    test('a transitive cluster shares one width and reuses freed lanes', () {
      expect(repartirEnCouloirs([iv(9, 0, 11, 0), iv(10, 0, 12, 0), iv(11, 0, 13, 0)]),
          [(couloir: 0, couloirs: 2), (couloir: 1, couloirs: 2), (couloir: 0, couloirs: 2)]);
    });
    test('input order is kept', () {
      expect(repartirEnCouloirs([iv(10, 0, 11, 0), iv(9, 0, 12, 0)]),
          [(couloir: 1, couloirs: 2), (couloir: 0, couloirs: 2)]);
    });
    test('a gap starts a fresh cluster', () {
      expect(repartirEnCouloirs([iv(9, 0, 10, 0), iv(9, 0, 10, 0), iv(14, 0, 15, 0)]).last,
          (couloir: 0, couloirs: 1));
    });
  });

  group('calendar arithmetic', () {
    test('week starts on Monday for a Monday-first locale', () {
      // Wednesday 14 October 2026.
      expect(debutDeSemaine(DateTime(2026, 10, 14, 15), 1), DateTime(2026, 10, 12));
    });
    test('week starts on Sunday for a Sunday-first locale', () {
      expect(debutDeSemaine(DateTime(2026, 10, 14), 0), DateTime(2026, 10, 11));
    });
    test('a Sunday in a Monday-first locale belongs to the week before', () {
      expect(debutDeSemaine(DateTime(2026, 10, 18), 1), DateTime(2026, 10, 12));
    });
    test('the month grid has 42 days and starts on the first weekday', () {
      final jours = joursDeLaGrilleDuMois(DateTime(2026, 10, 14), 1);
      expect(jours, hasLength(42));
      expect(jours.first, DateTime(2026, 9, 28)); // Monday before 1 October
      expect(jours.first.weekday, DateTime.monday);
    });
    test('day steps survive a DST change', () {
      // Europe switches back on 25 October 2026; adding days keeps midnight.
      expect(plusJours(DateTime(2026, 10, 24), 2), DateTime(2026, 10, 26));
    });
    test('month steps clamp the day', () {
      expect(plusMois(DateTime(2027, 1, 31), 1), DateTime(2027, 2, 28));
      expect(plusMois(DateTime(2026, 12, 15), 1), DateTime(2027, 1, 15));
    });
  });
}
