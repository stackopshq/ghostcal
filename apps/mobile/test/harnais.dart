import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import 'package:ghostcal/l10n/generated/app_localisations.dart';

/// Monte un écran **comme la production le monte**.
///
/// Depuis que les textes passent par `L.of(context)`, un `MaterialApp` nu ne suffit plus :
/// `Localizations.of<L>` y rend `null`, et le premier écran qui demande un libellé meurt
/// sur « Null check operator used on a null value ». Le message ne nomme ni la
/// localisation, ni le délégué manquant — il désigne l'écran, qui n'y est pour rien.
///
/// Deux tests l'ont appris d'un coup. Plutôt que de recopier la liste des délégués dans
/// chacun, elle vit ici : un test qui monte un écran autrement mesurerait une application
/// qui n'existe pas.
///
/// [locale] est **imposée** et vaut le français par défaut. Sans elle, l'environnement de
/// test retombe sur `en_US`, et une assertion sur un libellé français échouerait pour une
/// raison qui n'a rien à voir avec ce qu'elle croit mesurer. Les tests qui veulent
/// éprouver l'anglais la passent explicitement.
Widget appDEpreuve(Widget ecran, {Locale locale = const Locale('fr')}) => MaterialApp(
      locale: locale,
      localizationsDelegates: const [
        L.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: L.supportedLocales,
      home: ecran,
    );
