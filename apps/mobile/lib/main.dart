import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
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

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'GhostCal',
      debugShowCheckedModeBanner: false,
      theme: themeGhostcal(Brightness.light),
      darkTheme: themeGhostcal(Brightness.dark),
      // Sans ces trois lignes, les composants **d'Apple et de Flutter** restent en
      // anglais, sur un iPhone pourtant réglé en français : le sélecteur de date affiche
      // « Select date », « CANCEL », « OK », et les noms de jours y sont anglais. On
      // obtient un écran de création d'événement à moitié traduit — sur le parcours
      // principal du produit, celui que l'examinateur d'Apple verra en premier.
      //
      // Ce n'est pas la francisation de l'application, qui est faite : ses propres textes
      // sont en dur en français. C'est celle de ce que Flutter fournit.
      //
      // `supportedLocales` ne déclare **que** le français. Y ajouter l'anglais ferait
      // basculer les composants système en anglais sur un appareil réglé ainsi, pendant
      // que les textes de l'application resteraient français — un mélange pire que le
      // tout-français. Le jour où les textes seront extraits en `.arb`, cette liste
      // s'allongera en même temps qu'eux, pas avant.
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: const [Locale('fr')],
      locale: const Locale('fr'),
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
