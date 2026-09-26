import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import 'l10n/generated/app_localisations.dart';
import 'package:intl/date_symbol_data_local.dart';

import 'ecrans/accueil.dart';
import 'ecrans/connexion.dart';
import 'services/session.dart';
import 'services/verrouillage.dart';
import 'src/rust/frb_generated.dart';
import 'theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Le pont vers le cœur Rust. Sans cet appel, la première dérivation de clé échoue à
  // l'exécution — pas à la compilation.
  await RustLib.init();
  // Les noms de jours et de mois en français. Sans cette initialisation, `DateFormat`
  // avec une locale explicite lève une exception au premier affichage de l'agenda.
  await initializeDateFormatting('fr_FR');
  final session = Session();
  await session.amorcer();
  final verrouillage = Verrouillage();
  await verrouillage.amorcer();
  runApp(GhostcalApp(session: session, verrouillage: verrouillage));
}

class GhostcalApp extends StatelessWidget {
  const GhostcalApp({
    super.key,
    required this.session,
    required this.verrouillage,
    this.accueilDEpreuve,
    this.locale,
  });

  final Session session;
  final Verrouillage verrouillage;

  /// Un enfant substitué à l'arbitrage connexion/accueil, pour les seuls tests.
  ///
  /// `test/langue_test.dart` mesure la langue des composants fournis par Flutter, ce qui
  /// demande un contexte **sous** `MaterialApp` — et rien de plus. Passer par l'écran de
  /// connexion le rendrait tributaire de cet écran : un libellé renommé ferait rougir un
  /// test de localisation, ce qui n'aiderait personne à comprendre ce qui a cassé.
  ///
  /// `null` en production, donc sans effet sur ce qui est livré.
  final Widget? accueilDEpreuve;

  /// La langue à imposer, pour les seuls tests.
  ///
  /// `null` en production : l'application suit alors le réglage de l'appareil, ce qui est
  /// le comportement voulu depuis qu'elle parle deux langues. `test/langue_test.dart` s'en
  /// sert pour éprouver le français et l'anglais dans le même processus — sans quoi il
  /// faudrait deux exécutions et un réglage global, et le test mesurerait l'environnement
  /// plutôt que l'application.
  final Locale? locale;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'GhostCal',
      debugShowCheckedModeBanner: false,
      theme: themeGhostcal(Brightness.light),
      darkTheme: themeGhostcal(Brightness.dark),
      // Sans ces délégués, les composants **fournis par Flutter** restent en anglais sur
      // un appareil réglé en français : le sélecteur de date affiche « Select date »,
      // « CANCEL », « OK », et les jours y sont notés S M T W T F S. On obtenait un écran
      // de création d'événement à moitié traduit — sur le parcours principal du produit,
      // celui que l'examinateur d'Apple voit en premier.
      //
      // `L.delegate` porte les textes de l'application, les trois autres ceux de Flutter.
      // Les quatre sont nécessaires : traduire les nôtres sans les siens laisserait les
      // sélecteurs en anglais, et l'inverse laisserait les écrans en français.
      localizationsDelegates: const [
        L.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      // Français et anglais, comme GhostPass sur iOS et sur Android.
      //
      // La liste vient de `L.supportedLocales`, donc des fichiers `.arb`, et n'est pas
      // recopiée à la main : une langue ajoutée aux traductions sans l'être ici se
      // chargerait pour rien, et rien ne le dirait.
      supportedLocales: L.supportedLocales,
      locale: locale,
      // Le repli, rendu explicite.
      //
      // Sans cette fonction, Flutter retient la **première** langue de
      // `supportedLocales` quand aucune ne correspond. Or `gen-l10n` classe cette liste
      // par ordre alphabétique : « en » y précède « fr », et un iPhone réglé en allemand
      // se retrouvait en anglais. Mesuré, pas supposé.
      //
      // Ce n'était pas un choix, c'était l'ordre de l'alphabet. GhostCal est écrit en
      // français et vendu d'abord en Suisse romande : le français est le repli, et il
      // l'est maintenant pour une raison qu'on peut relire.
      localeResolutionCallback: (demandee, soutenues) {
        if (demandee != null) {
          for (final soutenue in soutenues) {
            if (soutenue.languageCode == demandee.languageCode) return soutenue;
          }
        }
        return const Locale('fr');
      },
      // Pas de `locale` imposée : on suit le réglage de l'appareil. Tant qu'une seule
      // langue existait, l'imposer évitait qu'un appareil réglé autrement retombe sur le
      // français par résolution implicite — un bon résultat obtenu par accident. Avec deux
      // langues, l'imposer reviendrait à ignorer le choix de l'utilisateur.
      home: accueilDEpreuve ??
          AnimatedBuilder(
            animation: session,
            builder: (context, _) => session.etat == Etat.ouvert
                ? EcranDAccueil(session: session, verrouillage: verrouillage)
                : EcranDeConnexion(session: session),
          ),
    );
  }
}
