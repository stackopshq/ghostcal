import 'dart:ui' show Locale, PlatformDispatcher;

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart'
    show MethodChannel, MissingPluginException, PlatformException;
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:timezone/timezone.dart' as tz;
import 'package:workmanager/workmanager.dart';

import '../l10n/generated/app_localisations.dart';
import '../modeles/adresse.dart';
import 'api.dart';
import 'apparence.dart';
import 'trousseau.dart';

/// How long before a booking the reminder fires.
enum AvanceDuRappel {
  cinq(5),
  dix(10),
  quinze(15),
  trente(30);

  const AvanceDuRappel(this.minutes);
  final int minutes;
}

/// One reminder to schedule: [quand] it fires, for the booking starting at [debut].
@immutable
class RappelPrevu {
  const RappelPrevu({
    required this.id,
    required this.quand,
    required this.debut,
  });

  final int id;
  final DateTime quand;
  final DateTime debut;
}

/// Which reminders the agenda rows call for.
///
/// Bookings only (`source == "booking"`), timed, and whose reminder is still ahead. Only
/// the start time is read: nothing about the invitee reaches the notification, whatever
/// the row carries. The id comes from the start minute, so two refreshes schedule the
/// same reminder once and two bookings at the same minute ring once.
List<RappelPrevu> rappelsAPrevoir(
  List<dynamic> lignes, {
  required DateTime maintenant,
  required Duration avance,
  int maximum = Rappels.maximum,
}) {
  final parId = <int, RappelPrevu>{};
  for (final ligne in lignes.whereType<Map<String, dynamic>>()) {
    if (ligne['source'] != 'booking' || ligne['all_day'] == true) continue;
    final debut = DateTime.tryParse('${ligne['start']}')?.toUtc();
    if (debut == null) continue;
    final quand = debut.subtract(avance);
    if (!quand.isAfter(maintenant)) continue;
    final id =
        (debut.millisecondsSinceEpoch ~/ Duration.millisecondsPerMinute) &
        0x7fffffff;
    parId[id] = RappelPrevu(id: id, quand: quand, debut: debut);
  }
  final tries = parId.values.toList()
    ..sort((a, b) => a.quand.compareTo(b.quand));
  return tries.take(maximum).toList();
}

/// Ce que le système répond quand on lui demande où en est le droit de notifier.
///
/// Les noms viennent du Swift, pas d'un rang : un entier se recopierait de travers le jour
/// où Apple ajoute un cas, et sans rien casser à la compilation.
enum EtatDesNotifications {
  /// L'alerte n'a jamais été présentée. C'est le seul état où la demander sert à quelque
  /// chose.
  jamaisDemande,

  /// Refusé — par l'utilisateur, ou par le système qui n'a jamais posé la question.
  /// L'alerte ne reparaîtra pas : la correction est dans les Réglages Système.
  refuse,

  accorde,
  provisoire,

  /// Un cas qu'Apple a ajouté depuis. On ne devine pas ce qu'il veut dire.
  inconnu,
}

/// Neutral booking reminders, computed and shown on the device.
///
/// - **No push service.** Notifications are scheduled locally; no third party learns
///   when a booking happens.
/// - **Neutral text.** "Appointment in 10 min": no invitee, no title, no place. Only
///   start times are read, and the server already holds them in the clear, so the vault
///   does not need to be open — a background refresh can run with the screen off.
/// - **Opt-in.** Off by default; the permission is asked when the user turns it on.
///
/// ─── Android and iOS, by two different routes ───
///
/// Android keeps a WorkManager task that re-reads the week every fifteen minutes, its
/// floor. iOS has no equivalent worth relying on: `BGAppRefreshTask` is opportunistic —
/// the system decides, the interval is not a promise, and a phone left alone can skip it
/// for hours. A reminder that depends on it would simply not ring.
///
/// So iOS does not refresh in the background at all. It schedules the **whole** window up
/// front — the system then holds the notifications, through a reboot, with the app never
/// running — and rebuilds that set whenever the app comes to the front, which
/// `EcranDAccueil` already does on `resumed`. The price is bounded and known: a booking
/// taken while the app is closed waits for the next opening to get its reminder.
///
/// ─── Ce que macOS fait autrement, et ce qu'il ne fait pas ───
///
/// Les bannières sont les mêmes : `flutter_local_notifications` les programme auprès du
/// centre de notifications, qui les présente à l'heure dite même application fermée.
///
/// Le **rafraîchissement**, lui, n'a pas d'équivalent. `workmanager` passe sur macOS par
/// `NSBackgroundActivityScheduler`, et sa documentation est explicite : les tâches
/// « run while the app is running/backgrounded; not after quit ». Là où Android réveille
/// un téléphone fermé, macOS ne réveille rien.
///
/// D'où [lancerALOuvertureDeSession], propre à macOS et éteint par défaut : il inscrit
/// l'application aux ouvertures de session, où elle démarre **sans fenêtre** et rend au
/// rafraîchissement l'occasion de tourner. Sans lui, les rappels ne sont replanifiés qu'à
/// l'ouverture de l'application — une réservation prise pendant que le Mac dort n'aura
/// donc pas de bannière avant qu'on la rouvre. C'est dit dans le réglage plutôt que laissé
/// à découvrir.
class Rappels extends ChangeNotifier {
  Rappels({FlutterLocalNotificationsPlugin? plugin, this._taches})
    : _plugin = plugin ?? FlutterLocalNotificationsPlugin();

  final FlutterLocalNotificationsPlugin _plugin;
  final Workmanager? _taches;
  Workmanager get _gestionnaire => _taches ?? Workmanager();

  static const _cleActif = 'ghostcal.rappels.actif';
  static const _cleAvance = 'ghostcal.rappels.avance';
  static const _cleOrganisation = 'ghostcal.rappels.organisation';
  static const _canal = 'ghostcal.bookings';
  static const _tache = 'ghostcal.rappels.rafraichir';

  /// How far ahead reminders are scheduled, and how many at most: Android caps the
  /// alarms one app may hold, and a refresh comes long before a week runs out.
  ///
  /// Fifty also clears iOS's own ceiling, which is harder: iOS keeps **64** pending
  /// local notifications per app and silently drops the rest. Since iOS schedules the
  /// entire window at once instead of refreshing, that ceiling is the real bound, and
  /// fifty leaves room under it rather than discovering it on a busy week.
  static const horizon = Duration(days: 7);
  static const maximum = 50;

  /// How often the background refresh runs. Fifteen minutes is Android's floor.
  static const frequence = Duration(minutes: 15);

  static bool get disponible =>
      !kIsWeb &&
      (defaultTargetPlatform == TargetPlatform.android ||
          defaultTargetPlatform == TargetPlatform.iOS ||
          defaultTargetPlatform == TargetPlatform.macOS);

  /// Android holds the exact-alarm permission and its own notification prompt.
  static bool get _surAndroid =>
      !kIsWeb && defaultTargetPlatform == TargetPlatform.android;

  /// Where the periodic refresh runs: WorkManager on Android, NSBackgroundActivityScheduler
  /// on macOS (only while the app runs, see above). iOS has none.
  static bool get _avecRafraichissement => _surAndroid || surMacos;

  /// Le canal des quelques choses que le greffon ne fait pas ici : l'inscription aux
  /// ouvertures de session. Public pour qu'un témoin le feigne sans le recopier.
  static const canalMacos = 'ch.stackops.ghostcal/rappels';

  /// Public : l'écran des réglages n'affiche l'inscription à l'ouverture de session que
  /// là où elle existe, et il ne peut pas la déduire de [aLOuvertureDeSession] — faux sur
  /// un Mac veut aussi dire « éteint ».
  static bool get surMacos =>
      !kIsWeb && defaultTargetPlatform == TargetPlatform.macOS;

  bool _actif = false;
  bool get actif => _actif;

  AvanceDuRappel _avance = AvanceDuRappel.dix;
  AvanceDuRappel get avance => _avance;

  bool _pret = false;

  /// Combien de rappels le système tient réellement en attente, relu après chaque
  /// planification. `null` tant que rien n'a été tenté.
  ///
  /// Ce n'est pas une statistique, c'est le seul moyen de savoir. Mesuré sur simulateur :
  /// `zonedSchedule` sur iOS **n'enregistre rien** quand l'autorisation manque, sans lever
  /// ni rien rendre. Un rappel qui ne sonne pas est alors indiscernable d'un agenda sans
  /// rendez-vous à venir — c'est précisément le doute qu'un utilisateur ne peut pas lever
  /// seul. Relire ce que le système tient le lève.
  int? _programmes;
  int? get programmes => _programmes;

  Future<void> amorcer() async {
    _actif = await Trousseau.lire(_cleActif) == 'true';
    final avance = await Trousseau.lire(_cleAvance);
    _avance = AvanceDuRappel.values.firstWhere(
      (v) => v.name == avance,
      orElse: () => AvanceDuRappel.dix,
    );
    _aLOuvertureDeSession =
        await _demanderAuSysteme<bool>('lanceALOuvertureDeSession') ?? false;
    notifyListeners();
  }

  /// Turns reminders on. False when the user refused the permission: the setting then
  /// stays off rather than claiming reminders that will never show.
  Future<bool> activer() async {
    await _preparer();
    if (!await _demanderLAutorisation()) return false;
    _actif = true;
    notifyListeners();
    await Trousseau.poser('true', _cleActif);
    // Rien de périodique sur iOS : voir l'en-tête de la classe. La fenêtre entière est
    // planifiée par `replanifier`, que l'écran d'accueil appelle à chaque retour.
    if (_avecRafraichissement) {
      await _gestionnaire.registerPeriodicTask(
        _tache,
        _tache,
        frequency: frequence,
        constraints: Constraints(networkType: NetworkType.connected),
        existingWorkPolicy: ExistingPeriodicWorkPolicy.update,
      );
    }
    return true;
  }

  /// Demande le droit de notifier, et rend ce que l'utilisateur a répondu.
  ///
  /// Les deux systèmes le demandent à cet instant précis et pas à l'amorçage : une
  /// application qui réclame une autorisation au premier lancement, pour une fonction
  /// que personne n'a allumée, se fait refuser — et le refus, sur iOS, ne se redemande
  /// pas. C'est pourquoi `DarwinInitializationSettings` ne demande rien.
  Future<bool> _demanderLAutorisation() async {
    if (_surAndroid) {
      final android = _plugin
          .resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin
          >();
      return await android?.requestNotificationsPermission() ?? false;
    }
    if (surMacos) {
      // `alert` and `sound`, no `badge`: a Dock badge would outlive the banner.
      final macos = _plugin
          .resolvePlatformSpecificImplementation<
            MacOSFlutterLocalNotificationsPlugin
          >();
      return await macos?.requestPermissions(alert: true, sound: true) ?? false;
    }
    final ios = _plugin
        .resolvePlatformSpecificImplementation<
          IOSFlutterLocalNotificationsPlugin
        >();
    // Pas de pastille : le compteur sur l'icône survivrait au rendez-vous et dirait
    // qu'il reste quelque chose à faire. Le son et la bannière suffisent à un rappel.
    return await ios?.requestPermissions(
          alert: true,
          badge: false,
          sound: true,
        ) ??
        false;
  }

  Future<void> desactiver() async {
    _actif = false;
    notifyListeners();
    await Trousseau.poser('false', _cleActif);
    await arreter();
  }

  /// Stops the refresh and drops what is scheduled, keeping the user's choice: used at
  /// sign-out, so reminders resume with the next session.
  Future<void> arreter() async {
    if (_avecRafraichissement) await _gestionnaire.cancelByUniqueName(_tache);
    await _preparer();
    await _plugin.cancelAllPendingNotifications();
    _programmes = null;
    notifyListeners();
  }

  // ─── Pourquoi l'autorisation a échoué, et où aller la corriger ───

  /// L'état du droit de notifier, demandé **au système**.
  ///
  /// `requestPermissions` rend un simple `false`, et ce `false` recouvre deux situations
  /// qui ne se corrigent pas de la même façon : on vient de refuser l'alerte, ou macOS ne
  /// l'a jamais posée parce qu'un refus est déjà enregistré. Dans le second cas l'alerte
  /// ne reparaîtra plus — le système n'en présente qu'une par application — et il faut
  /// passer par les Réglages Système. Dire « autorisez-les dans les réglages » sans
  /// distinguer les deux laisse chercher une alerte qui ne viendra jamais.
  ///
  /// `null` hors macOS : Android a son propre chemin, déjà traité par le greffon.
  Future<EtatDesNotifications?> etatDesNotifications() async {
    final brut = await _demanderAuSysteme<String>('etatDesNotifications');
    if (brut == null) return null;
    return EtatDesNotifications.values.firstWhere(
      (e) => e.name == brut,
      orElse: () => EtatDesNotifications.inconnu,
    );
  }

  /// Ouvre le volet des notifications des Réglages Système. Rend `false` si macOS n'a
  /// rien ouvert — l'écran se tait alors plutôt que de promettre un volet absent.
  Future<bool> ouvrirLesReglagesDesNotifications() async =>
      await _demanderAuSysteme<bool>('ouvrirLesReglagesDesNotifications') ??
      false;

  // ─── L'ouverture de session, sur macOS seulement ───

  bool _aLOuvertureDeSession = false;

  /// L'application est-elle inscrite aux ouvertures de session ?
  ///
  /// Toujours faux ailleurs que sur macOS, et faux tant qu'[amorcer] n'a pas demandé —
  /// car la réponse appartient au système et non à nous : elle se retire depuis les
  /// Réglages Système sans que l'application en soit avertie. Un réglage qui se souvient
  /// de ce qu'on lui a dit ment dès que la plateforme change d'avis.
  bool get aLOuvertureDeSession => _aLOuvertureDeSession;

  /// Inscrit ou retire l'application, et rend l'état **constaté après coup**.
  ///
  /// Pas la valeur demandée : `SMAppService.register()` peut échouer, l'utilisateur ayant
  /// pu interdire le lancement automatique depuis les Réglages Système. Rendre ce qu'on a
  /// demandé afficherait un interrupteur allumé devant un système qui a dit non.
  Future<bool> lancerALOuvertureDeSession(bool valeur) async {
    _aLOuvertureDeSession =
        await _demanderAuSysteme<bool>('lancerALOuvertureDeSession', {
          'valeur': valeur,
        }) ??
        false;
    notifyListeners();
    return _aLOuvertureDeSession;
  }

  /// L'appel de plateforme, qui ne jette pas là où le canal n'existe pas.
  ///
  /// Android n'a pas celui-ci : une `MissingPluginException` non rattrapée y ferait
  /// échouer [amorcer], donc le lancement de l'application, pour un réglage qui n'y existe
  /// pas.
  Future<T?> _demanderAuSysteme<T>(
    String methode, [
    Map<String, Object?>? arguments,
  ]) async {
    if (!surMacos) return null;
    try {
      return await const MethodChannel(canalMacos)
          .invokeMethod<T>(methode, arguments);
    } on MissingPluginException {
      return null;
    } on PlatformException {
      return null;
    }
  }

  Future<void> choisirLAvance(AvanceDuRappel valeur) async {
    _avance = valeur;
    notifyListeners();
    await Trousseau.poser(valeur.name, _cleAvance);
  }

  /// Fetches the next week of bookings and schedules their reminders, replacing the
  /// previous set. Does nothing while reminders are off.
  Future<void> replanifier(ClientAPI api, {String? organisation}) async {
    if (!_actif) return;
    if (organisation != null) {
      await Trousseau.poser(organisation, _cleOrganisation);
    }
    final maintenant = DateTime.now().toUtc();
    final lignes = await api.obtenir<List<dynamic>>('v1/me/calendar/agenda', {
      'from': maintenant.toIso8601String(),
      'to': maintenant.add(horizon).toIso8601String(),
    });
    final prevus = rappelsAPrevoir(
      lignes,
      maintenant: maintenant,
      avance: Duration(minutes: _avance.minutes),
    );
    await _planifier(prevus);
  }

  /// The background entry point: rebuilds a client from the keychain, without the vault.
  static Future<void> depuisLeFond() async {
    final rappels = Rappels();
    await rappels.amorcer();
    if (!rappels.actif) return;
    final base = AdresseDeServeur.normaliser(
      await Trousseau.lire(Trousseau.serveur) ?? '',
    );
    final jetons = await Trousseau.jetons();
    if (base == null || jetons == null) {
      // Signed out: nothing should ring for an account that is no longer here.
      await rappels.arreter();
      return;
    }
    final client = ClientAPI(base: base)
      ..poserLesJetons(jetons)
      ..poserLOrganisation(await Trousseau.lire(_cleOrganisation))
      ..auRenouvellement = Trousseau.poserLesJetons
      ..relireLesJetons = Trousseau.jetons;
    await rappels.replanifier(client);
  }

  Future<void> _planifier(List<RappelPrevu> prevus) async {
    await _preparer();
    await _plugin.cancelAllPendingNotifications();
    if (prevus.isEmpty) {
      await _relireCeQuiEstEnAttente();
      return;
    }

    final l = await _langue();
    final android = _plugin
        .resolvePlatformSpecificImplementation<
          AndroidFlutterLocalNotificationsPlugin
        >();
    final exact = await android?.canScheduleExactNotifications() ?? false;
    final details = NotificationDetails(
      // Rien à régler sur iOS pour masquer le texte à l'écran verrouillé : c'est un
      // réglage de l'utilisateur (« Afficher les aperçus »), qu'aucune application ne
      // commande. La neutralité du texte est donc la seule garantie qui tienne des deux
      // côtés — et c'est celle que `rappels_test.dart` mesure.
      iOS: const DarwinNotificationDetails(
        presentAlert: true,
        presentBadge: false,
        presentSound: true,
        // `active` et non `timeSensitive`, bien qu'un rendez-vous imminent en relève :
        // le niveau Time Sensitive **exige** le droit
        // `com.apple.developer.usernotifications.time-sensitive`, que cette application
        // ne déclare pas — vérifié sur la build signée, qui ne porte aucun entitlement.
        //
        // Sans le droit, iOS rétrograde silencieusement le niveau. Le rappel sonnerait
        // donc quand même, et c'est ce qui rend la demande trompeuse plutôt qu'inoffensive :
        // le code promettrait de percer un mode de concentration, ce qu'il ne fait pas.
        //
        // Y revenir demande d'activer la capacité dans le compte développeur et de la
        // déclarer ici : une décision de provisionnement, pas une constante à changer.
        interruptionLevel: InterruptionLevel.active,
      ),
      android: AndroidNotificationDetails(
        _canal,
        l.rappelsCanal,
        channelDescription: l.rappelsCanalDescription,
        importance: Importance.high,
        priority: Priority.high,
        category: AndroidNotificationCategory.reminder,
        // The text is neutral already; hiding it on a locked screen costs nothing.
        visibility: NotificationVisibility.private,
      ),
      // macOS n'a ni canal ni visibilité d'écran verrouillé : ce qu'il montre se règle
      // dans les Réglages Système, par application. Il ne reste donc à dire que la forme
      // de la présentation — et pas de pastille, pour la raison donnée dans [activer].
      macOS: const DarwinNotificationDetails(
        presentAlert: true,
        presentBanner: true,
        presentSound: true,
        presentBadge: false,
      ),
    );
    for (final prevu in prevus) {
      await _plugin.zonedSchedule(
        id: prevu.id,
        scheduledDate: tz.TZDateTime.from(prevu.quand, tz.UTC),
        notificationDetails: details,
        androidScheduleMode: exact
            ? AndroidScheduleMode.exactAllowWhileIdle
            : AndroidScheduleMode.inexactAllowWhileIdle,
        title: l.rappelTitre,
        body: l.rappelCorps(prevu.debut.difference(prevu.quand).inMinutes),
      );
    }
    await _relireCeQuiEstEnAttente();
  }

  /// Relit ce que le système tient, plutôt que de compter ce qu'on a demandé.
  ///
  /// La différence est tout l'intérêt : sur iOS une demande refusée ne lève pas, et sur
  /// les deux plateformes un plafond atteint écarte les suivantes en silence.
  Future<void> _relireCeQuiEstEnAttente() async {
    try {
      _programmes = (await _plugin.pendingNotificationRequests()).length;
    } on Object {
      _programmes = null;
    }
    notifyListeners();
  }

  Future<void> _preparer() async {
    if (_pret) return;
    await _plugin.initialize(
      settings: const InitializationSettings(
        android: AndroidInitializationSettings('ic_notification'),
        // Aucune demande ici : `activer()` s'en charge, au moment où l'utilisateur
        // allume la fonction. iOS n'a pas d'icône à nommer, il prend celle de l'app.
        iOS: DarwinInitializationSettings(
          requestAlertPermission: false,
          requestBadgePermission: false,
          requestSoundPermission: false,
        ),
        // Les trois demandes sont **coupées** : l'autorisation se demande dans [activer],
        // au moment où quelqu'un allume le réglage. Les laisser à leur défaut la ferait
        // surgir au premier lancement, devant quelqu'un qui n'a pas encore vu à quoi sert
        // l'application — et macOS ne repose pas la question après un refus.
        macOS: DarwinInitializationSettings(
          requestAlertPermission: false,
          requestSoundPermission: false,
          requestBadgePermission: false,
        ),
      ),
    );
    _pret = true;
  }

  /// The language picked in the settings, else the device's. No widget tree here: the
  /// background isolate has none.
  static Future<L> _langue() async {
    final choisie = await Trousseau.lire(Apparence.cleLangue);
    final code =
        ChoixDeLangue.values
            .where((v) => v.name == choisie)
            .firstOrNull
            ?.locale
            ?.languageCode ??
        PlatformDispatcher.instance.locale.languageCode;
    return lookupL(Locale(code == 'en' ? 'en' : 'fr'));
  }
}

/// Runs in a background isolate, started by WorkManager.
@pragma('vm:entry-point')
void tacheDeFond() {
  Workmanager().executeTask((_, _) async {
    try {
      await Rappels.depuisLeFond();
    } on Object catch (e) {
      // Offline or the session ended: the next run tries again, and the reminders
      // already scheduled still ring.
      debugPrint('ghostcal.rappels: background refresh failed: $e');
    }
    return true;
  });
}
