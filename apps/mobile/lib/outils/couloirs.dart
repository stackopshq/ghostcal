/// Side-by-side layout for timed events that overlap in one day column, the way
/// Fantastical and Google Calendar draw them. Same algorithm as the web
/// (`frontend/src/lib/eventLayout.ts`), so both clients agree on what a day looks like.
library;

/// The lane an interval sits in, and how many lanes its overlap cluster has.
typedef Couloir = ({int couloir, int couloirs});

/// Assigns each interval a lane (0-based) and the lane count of its overlap cluster.
///
/// A cluster is a run of intervals linked by overlap, transitively, so widths stay
/// aligned inside it. Each interval takes the first lane free at its start. Touching
/// intervals (one ends when the next starts) do not overlap. Returns one entry per
/// input, in input order.
List<Couloir> repartirEnCouloirs(List<({DateTime debut, DateTime fin})> intervalles) {
  final ordre = List<int>.generate(intervalles.length, (i) => i)
    ..sort((a, b) {
      final parDebut = intervalles[a].debut.compareTo(intervalles[b].debut);
      return parDebut != 0 ? parDebut : intervalles[b].fin.compareTo(intervalles[a].fin);
    });

  final couloirDe = List<int>.filled(intervalles.length, 0);
  final nombreDe = List<int>.filled(intervalles.length, 1);
  var grappe = <int>[];
  var finsDesCouloirs = <DateTime>[];
  DateTime? finDeGrappe;

  void fermer() {
    for (final i in grappe) {
      nombreDe[i] = finsDesCouloirs.length;
    }
    grappe = [];
    finsDesCouloirs = [];
  }

  for (final i in ordre) {
    final iv = intervalles[i];
    if (finDeGrappe != null && !iv.debut.isBefore(finDeGrappe)) fermer();
    var couloir = finsDesCouloirs.indexWhere((fin) => !fin.isAfter(iv.debut));
    if (couloir == -1) {
      finsDesCouloirs.add(iv.fin);
      couloir = finsDesCouloirs.length - 1;
    } else {
      finsDesCouloirs[couloir] = iv.fin;
    }
    couloirDe[i] = couloir;
    grappe.add(i);
    finDeGrappe = finDeGrappe == null || iv.fin.isAfter(finDeGrappe) ? iv.fin : finDeGrappe;
  }
  fermer();
  return [
    for (var i = 0; i < intervalles.length; i++) (couloir: couloirDe[i], couloirs: nombreDe[i]),
  ];
}
