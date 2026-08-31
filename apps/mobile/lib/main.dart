import 'package:flutter/material.dart';
import 'package:intl/date_symbol_data_local.dart';

import 'ecrans/accueil.dart';
import 'ecrans/connexion.dart';
import 'services/session.dart';
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
  runApp(GhostcalApp(session: session));
}

class GhostcalApp extends StatelessWidget {
  const GhostcalApp({super.key, required this.session});

  final Session session;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'GhostCal',
      debugShowCheckedModeBanner: false,
      theme: themeGhostcal(Brightness.light),
      darkTheme: themeGhostcal(Brightness.dark),
      home: AnimatedBuilder(
        animation: session,
        builder: (context, _) => session.etat == Etat.ouvert
            ? EcranDAccueil(session: session)
            : EcranDeConnexion(session: session),
      ),
    );
  }
}
