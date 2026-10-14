import '../l10n/generated/app_localisations.dart';
import 'trousseau.dart';

/// How the agenda is shown. The user's choice, remembered between launches.
enum VueDAgenda {
  jour,
  semaine,
  mois,
  liste;

  String libelle(L l) => switch (this) {
        VueDAgenda.jour => l.vueJour,
        VueDAgenda.semaine => l.vueSemaine,
        VueDAgenda.mois => l.vueMois,
        VueDAgenda.liste => l.vueListe,
      };

  static const _cle = 'ghostcal.agenda.vue';

  /// The saved view; the day view when nothing (or something unknown) is saved.
  static Future<VueDAgenda> retenue() async {
    try {
      final brut = await Trousseau.lire(_cle);
      return VueDAgenda.values.firstWhere((v) => v.name == brut,
          orElse: () => VueDAgenda.jour);
    } on Object {
      return VueDAgenda.jour;
    }
  }

  Future<void> retenir() async {
    try {
      await Trousseau.poser(name, _cle);
    } on Object {
      // A preference that fails to save is not worth an error on screen.
    }
  }
}
