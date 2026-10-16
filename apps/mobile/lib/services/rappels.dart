import 'dart:ui' show Locale, PlatformDispatcher;

import 'package:flutter/foundation.dart';
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
          defaultTargetPlatform == TargetPlatform.iOS);

  /// Android holds the periodic refresh and the exact-alarm permission; iOS has neither.
  static bool get _surAndroid =>
      !kIsWeb && defaultTargetPlatform == TargetPlatform.android;

  bool _actif = false;
  bool get actif => _actif;

  AvanceDuRappel _avance = AvanceDuRappel.dix;
  AvanceDuRappel get avance => _avance;

  bool _pret = false;

  Future<void> amorcer() async {
    _actif = await Trousseau.lire(_cleActif) == 'true';
    final avance = await Trousseau.lire(_cleAvance);
    _avance = AvanceDuRappel.values.firstWhere(
      (v) => v.name == avance,
      orElse: () => AvanceDuRappel.dix,
    );
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
    if (_surAndroid) {
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
    final ios = _plugin
        .resolvePlatformSpecificImplementation<
          IOSFlutterLocalNotificationsPlugin
        >();
    // Pas de pastille : le compteur sur l'icône survivrait au rendez-vous et dirait
    // qu'il reste quelque chose à faire. Le son et la bannière suffisent à un rappel.
    return await ios?.requestPermissions(alert: true, badge: false, sound: true) ??
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
    if (_surAndroid) await _gestionnaire.cancelByUniqueName(_tache);
    await _preparer();
    await _plugin.cancelAllPendingNotifications();
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
    if (prevus.isEmpty) return;

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
        interruptionLevel: InterruptionLevel.timeSensitive,
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
