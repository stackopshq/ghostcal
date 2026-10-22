import 'package:flutter/foundation.dart'
    show TargetPlatform, defaultTargetPlatform, kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import 'l10n/generated/app_localisations.dart';

import 'package:intl/date_symbol_data_local.dart';
import 'package:workmanager/workmanager.dart';

import 'ecrans/accueil.dart';
import 'ecrans/connexion.dart';
import 'services/apparence.dart';
import 'services/rappels.dart';
import 'services/session.dart';
import 'services/verrouillage.dart';
import 'src/rust/frb_generated.dart';
import 'theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Le pont vers le cœur Rust. Sans cet appel, la première dérivation de clé échoue à
  // l'exécution — pas à la compilation.
  await RustLib.init();
  // Day and month names for every supported language: dates follow the screen's
  // language. Without this, `DateFormat` with an explicit locale throws on first use.
  await initializeDateFormatting();
  final session = Session();
  await session.amorcer();
  final verrouillage = Verrouillage();
  await verrouillage.amorcer();
  final apparence = Apparence();
  await apparence.amorcer();
  // La langue suit la session, et continue de la suivre : posée maintenant pour le client
  // API qui naîtra à la connexion, et reposée chaque fois qu'on en change dans les
  // réglages. Sans le second, changer de langue n'aurait d'effet qu'au prochain lancement.
  session.poserLaLangue(apparence.codeDeLangue);
  apparence.addListener(() => session.poserLaLangue(apparence.codeDeLangue));
  Rappels? rappels;
  if (Rappels.disponible) {
    // Seulement là où une tâche périodique existe : `Workmanager` sur iOS s'appuie sur
    // `BGTaskScheduler`, qui exige des identifiants déclarés dans l'Info.plist et ne
    // promet aucun intervalle. Les rappels iOS n'en dépendent pas — voir `Rappels`.
    if (defaultTargetPlatform == TargetPlatform.android) {
      await Workmanager().initialize(tacheDeFond);
    }
    rappels = Rappels();
    await rappels.amorcer();
    session.avantDeSortir = rappels.arreter;
  }
  runApp(
    GhostcalApp(
      session: session,
      verrouillage: verrouillage,
      apparence: apparence,
      rappels: rappels,
    ),
  );
}

/// Le navigateur de l'application. De portée fichier, parce qu'il n'y en a qu'un, et
/// nécessaire : `_RetirerLesEcransAuVerrouillage` se place **au-dessus** du navigateur,
/// là où `Navigator.of(context)` ne le trouverait pas.
final _navigateur = GlobalKey<NavigatorState>();

class GhostcalApp extends StatelessWidget {
  const GhostcalApp({
    super.key,
    required this.session,
    required this.verrouillage,
    this.accueilDEpreuve,
    this.locale,
    this.apparence,
    this.rappels,
  });

  /// Booking reminders; `null` where they are not offered (iOS for now, tests).
  final Rappels? rappels;

  /// Language and theme picked in the settings. Optional so tests can build the app
  /// without a keychain; `null` follows the device.
  final Apparence? apparence;

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
    final apparence = this.apparence;
    if (apparence == null) return _application(null);
    return ListenableBuilder(
      listenable: apparence,
      builder: (_, _) => _application(apparence),
    );
  }

  Widget _application(Apparence? apparence) {
    return MaterialApp(
      navigatorKey: _navigateur,
      title: 'GhostCal',
      debugShowCheckedModeBanner: false,
      theme: themeGhostcal(Brightness.light),
      darkTheme: themeGhostcal(Brightness.dark),
      themeMode: apparence?.theme.mode ?? ThemeMode.system,
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
      locale: locale ?? apparence?.langue.locale,
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
      // La barre d'état du système suit le thème **de l'application**, pas celui de
      // l'appareil. Voir `_BarreDEtatSelonLeTheme`, qui porte la mesure et les trois
      // chemins essayés avant celui-là.
      builder: (context, enfant) => _BarreDEtatSelonLeTheme(
        enfant: _RetirerLesEcransAuVerrouillage(
          session: session,
          enfant: enfant ?? const SizedBox.shrink(),
        ),
      ),
      home:
          accueilDEpreuve ??
          AnimatedBuilder(
            animation: session,
            builder: (context, _) => session.etat == Etat.ouvert
                ? EcranDAccueil(
                    session: session,
                    verrouillage: verrouillage,
                    apparence: apparence,
                    rappels: rappels,
                  )
                : EcranDeConnexion(session: session),
          ),
    );
  }
}

/// Retire les écrans empilés quand le coffre se referme.
///
/// ─── Le défaut que ce widget corrige ───
///
/// `home` change bien : `EcranDeConnexion` remplace `EcranDAccueil` dès que la session
/// n'est plus ouverte. Mais les écrans ouverts par `Navigator.push` — la recherche, le
/// détail d'un événement, une fiche — sont empilés **au-dessus** de `home`, sur le
/// navigateur de `MaterialApp`. Remplacer la route du bas ne les retire pas : ils
/// restent affichés, avec leur contenu déchiffré, par-dessus un coffre verrouillé.
///
/// Mesuré le 2026-10-20 par `integration_test/macos_test.dart`, et non déduit : coffre
/// verrouillé, `EcranDeConnexion` monté, `EcranDAccueil` démonté — et l'écran de
/// recherche toujours **visible** au premier plan.
///
/// Le verrouillage automatique au retour d'arrière-plan emprunte le même appel, donc le
/// défaut n'avait pas besoin d'un raccourci clavier pour se produire : il suffisait de
/// quitter l'application en laissant un événement ouvert. ⌘L l'a seulement rendu
/// immédiat, puis visible.
///
/// ─── Pourquoi ici, et pas dans l'écran d'accueil ───
///
/// `builder` enveloppe le navigateur ; ce widget vit donc au-dessus des routes et
/// survit au changement de `home`. Un garde posé dans `EcranDAccueil` serait démonté
/// par le changement même qu'il doit traiter, et dépendrait de l'ordre dans lequel les
/// auditeurs du `Session` sont appelés.
class _RetirerLesEcransAuVerrouillage extends StatefulWidget {
  const _RetirerLesEcransAuVerrouillage({
    required this.session,
    required this.enfant,
  });

  final Session session;
  final Widget enfant;

  @override
  State<_RetirerLesEcransAuVerrouillage> createState() => _EtatDuRetrait();
}

class _EtatDuRetrait extends State<_RetirerLesEcransAuVerrouillage> {
  /// L'état précédent, tenu à la main : `Session` prévient à chaque changement, et on
  /// ne doit dépiler qu'au **passage** d'ouvert à fermé. Dépiler à chaque notification
  /// renverrait l'utilisateur à l'agenda au moindre rafraîchissement.
  late Etat _etat = widget.session.etat;

  @override
  void initState() {
    super.initState();
    widget.session.addListener(_surChangement);
  }

  @override
  void dispose() {
    widget.session.removeListener(_surChangement);
    super.dispose();
  }

  void _surChangement() {
    final avant = _etat;
    _etat = widget.session.etat;
    if (avant != Etat.ouvert || _etat == Etat.ouvert) return;
    // Après la trame : dépiler pendant la notification reconstruirait le navigateur au
    // milieu de sa propre mise à jour.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _navigateur.currentState?.popUntil((route) => route.isFirst);
    });
  }

  @override
  Widget build(BuildContext context) => widget.enfant;
}

/// Donne à iOS le style de barre d'état qui va avec le thème **de l'application**.
///
/// ─── Pourquoi un canal natif et pas `SystemChrome` ───
///
/// En thème clair, l'heure et la batterie sortaient blanches sur fond pâle : 1,18:1 de
/// contraste, contre 18,73:1 en sombre. Vu sur l'iPhone comme sur le simulateur, et ce
/// n'était pas un artefact de capture — les Réglages d'iOS, photographiés au même endroit
/// par la même commande, rendent une horloge noire.
///
/// Trois correctifs par le chemin Flutter n'ont rien changé. Le quatrième essai a été
/// **instrumenté** plutôt que supposé, et la sonde a innocenté Dart :
///
///     SONDE: theme=Brightness.light plateforme=Brightness.light
///     SONDE: pose statusBarBrightness=Brightness.light
///
/// La bonne valeur était demandée, et la dalle restait blanche. `AnnotatedRegion`,
/// `SystemChrome.setSystemUIOverlayStyle` et `UIViewControllerBasedStatusBarAppearance`
/// à `false` ont tous laissé la mesure à 1,18:1. Le passage par `SystemChrome` ne tient
/// pas sur cette version d'iOS.
///
/// `ControleurGhostcal` répond donc à `preferredStatusBarStyle`, le mécanisme d'UIKit,
/// que ce widget nourrit. Rien n'est envoyé ailleurs qu'iOS : sur Android la barre suit
/// déjà le thème, et le canal n'existe pas.
class _BarreDEtatSelonLeTheme extends StatefulWidget {
  const _BarreDEtatSelonLeTheme({required this.enfant});

  final Widget enfant;

  @override
  State<_BarreDEtatSelonLeTheme> createState() => _EtatDeLaBarreDEtat();
}

class _EtatDeLaBarreDEtat extends State<_BarreDEtatSelonLeTheme> {
  static const _canal = MethodChannel('ch.stackops.ghostcal/symboles');

  Brightness? _posee;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (kIsWeb || defaultTargetPlatform != TargetPlatform.iOS) return;
    // `Theme.of` et non `platformBrightness` : c'est le thème que `themeMode` a résolu
    // qui est à l'écran, et c'est contre lui que la barre doit contraster. Les deux
    // divergent dès que l'utilisateur impose un thème — exactement le cas du défaut.
    final luminosite = Theme.of(context).brightness;
    if (luminosite == _posee) return;
    _posee = luminosite;
    // Sans attendre : un échec du canal ne doit pas retarder l'affichage, et il n'y a
    // rien à rattraper — la barre garde simplement son style précédent.
    _canal
        .invokeMethod<void>('barreDEtat', {
          'sombre': luminosite == Brightness.dark,
        })
        .catchError((Object _) {});
  }

  @override
  Widget build(BuildContext context) => widget.enfant;
}
