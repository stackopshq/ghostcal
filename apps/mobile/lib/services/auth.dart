import 'dart:convert';
import 'dart:typed_data';

import '../src/rust/api/coeur.dart' as coeur;
import 'api.dart';

/// Le compte demande un second facteur, et la connexion attend un code.
///
/// Un type à part plutôt qu'un message : l'écran doit OUVRIR un champ, pas
/// afficher une erreur. Confondre les deux est exactement ce qui se passait —
/// un mot de passe bon présenté comme refusé, sans issue.
class SecondFacteurRequis implements Exception {
  const SecondFacteurRequis({
    required this.genre,
    required this.message,
    this.codeRefuse = false,
    this.bloqueJusqua,
  });

  /// `totp` aujourd'hui. Lu et non supposé : le jour où le serveur en propose
  /// un second, un client qui aurait codé « c'est forcément du TOTP » afficherait
  /// le mauvais écran sans erreur.
  final String genre;

  final String message;

  /// Vrai quand un code a été présenté et refusé, faux quand il manquait. Les
  /// deux demandent la même chose à l'utilisateur mais ne se disent pas pareil.
  final bool codeRefuse;

  /// Trop d'essais : le serveur rend 429 et dit jusqu'à quand. Sans cela, un
  /// client réessaie en boucle sur une saisie qui ne peut pas aboutir.
  final DateTime? bloqueJusqua;

  bool get estBloque => bloqueJusqua != null;

  /// Reconnaît l'exigence dans une erreur d'API, ou rend nul si ce n'en est pas une.
  static SecondFacteurRequis? depuis(ErreurAPI e) {
    final d = e.details;
    if (d == null || d['mfa_required'] != true) return null;
    final quand = d['locked_until'];
    return SecondFacteurRequis(
      genre: d['mfa_type'] is String ? d['mfa_type'] as String : 'totp',
      message: e.message,
      codeRefuse: e.statut == 401 && '${d['detail']}'.contains('invalid'),
      bloqueJusqua: quand is String ? DateTime.tryParse(quand) : null,
    );
  }

  @override
  String toString() => message;
}

/// Les clés d'une organisation, une fois ouvertes.
///
/// `anterieures` porte les générations retirées : elles ne servent plus à sceller, mais
/// restent indispensables pour lire ce qui l'a été avant une rotation. Les oublier ferait
/// disparaître d'anciens rendez-vous sans le moindre message.
class ClesOuvertes {
  const ClesOuvertes({
    required this.organisation,
    required this.publique,
    required this.privee,
    this.anterieures = const [],
  });

  final String organisation;
  final String publique;
  final String privee;
  final List<String> anterieures;

  ClesOuvertes avecAnterieure(String privee) => ClesOuvertes(
        organisation: organisation,
        publique: publique,
        privee: this.privee,
        anterieures: [...anterieures, privee],
      );
}

/// Ce qui peut mal tourner en ouvrant une session.
class ErreurDAuth implements Exception {
  const ErreurDAuth(this.message);

  /// La phrase ne déballe aucune enveloppe.
  ///
  /// Le message ne nomme ni « mot de passe » ni « phrase de récupération » : les trois
  /// chemins — mot de passe, récupération, phrase de chiffrement d'un compte SSO —
  /// aboutissent ici, et nommer le mauvais enverrait chercher à côté.
  static const phraseIncorrecte = ErreurDAuth("Cette phrase n'ouvre pas le coffre.");

  /// On a tenté de sceller alors que les clés ne sont pas ouvertes. Distinct d'une phrase
  /// fausse : ici rien n'a été tenté, il n'y a simplement rien pour sceller.
  static const coffreFerme =
      ErreurDAuth('Le coffre est fermé : impossible de chiffrer ce contenu.');

  final String message;

  @override
  String toString() => message;
}

/// Ouvrir une session GhostCal.
///
/// Deux choses se passent à la connexion, et il faut les distinguer parce qu'elles
/// échouent séparément :
///
/// 1. **L'authentification** — le serveur rend une paire de jetons. Sans elle, rien.
/// 2. **Le déverrouillage du coffre** — la phrase dérive une clé qui déballe la clé privée
///    de l'organisation. Sans lui, l'authentification a réussi mais l'agenda reste
///    illisible.
///
/// Un échec du second ne doit **jamais** empêcher le premier. C'est le comportement du
/// client web, et il est juste : quelqu'un dont le déverrouillage échoue doit pouvoir
/// entrer, voir qu'il est connecté, et comprendre que c'est sa phrase qui ne va pas — pas
/// se faire renvoyer à l'écran de connexion sans explication.
///
/// Aucune cryptographie ici : tout passe par le cœur Rust partagé avec le web, iOS et
/// Android. Cette classe traduit des types, et rien d'autre.
class Auth {
  Auth(this.api);

  static const domaineGhostcal = 'ghostcal-zk-v1';

  final ClientAPI api;
  final Map<String, ClesOuvertes> _cles = {};

  ClesOuvertes? clesDe(String organisation) => _cles[organisation];

  /// Le coffre est-il ouvert ? Faux juste après une connexion dont le déverrouillage a
  /// échoué — d'où la distinction avec « connecté ».
  bool get estDeverrouille => _cles.isNotEmpty;

  List<String> get organisations => _cles.keys.toList();

  void verrouiller() => _cles.clear();

  /// Authentifie, puis tente d'ouvrir le coffre. Rend la raison d'un déverrouillage manqué
  /// plutôt que de la taire ; rend nul si tout s'est bien passé.
  ///
  /// Lève [SecondFacteurRequis] quand le compte en a un et que [codeTotp] manque
  /// ou ne convient pas. Sans ce cas, le serveur répondait 401 avec un `detail`
  /// OBJET que le client ne savait pas lire : l'écran affichait « Le serveur a
  /// répondu 401 » sur un mot de passe pourtant bon, et rien ne disait qu'il
  /// fallait un code. Le serveur porte `mfa_required` depuis que le TOTP est
  /// arrivé sur `main` ; le mobile, lui, ne le connaissait pas du tout.
  Future<String?> seConnecter({
    required String email,
    required String motDePasse,
    String? codeTotp,
  }) async {
    final Map<String, dynamic> json;
    try {
      json = await api.envoyer<Map<String, dynamic>>(
        'POST',
        'v1/auth/login',
        {
          'email': email,
          'password': motDePasse,
          // Absent et non vide : le serveur borne la longueur du champ, et une
          // chaîne vide n'est pas « pas de code ».
          if (codeTotp != null && codeTotp.isNotEmpty) 'totp_code': codeTotp,
        },
      );
    } on ErreurAPI catch (e) {
      final exigence = SecondFacteurRequis.depuis(e);
      if (exigence != null) throw exigence;
      rethrow;
    }
    api.poserLesJetons(Jetons(
      acces: '${json['access_token']}',
      rafraichissement: '${json['refresh_token']}',
    ));

    try {
      await deverrouiller(phrase: motDePasse);
      return null;
    } on ErreurDAuth catch (e) {
      // Connecté sans coffre ouvert : on le dit, on ne défait pas la connexion.
      return e.message;
    }
  }

  /// Dérive la clé depuis la phrase, déballe chaque génération de clé d'organisation.
  ///
  /// La phrase peut être le mot de passe, la phrase de récupération, ou la phrase de
  /// chiffrement d'un compte SSO : le serveur range deux enveloppes par génération, et
  /// c'est le sel qui les distingue, pas la nature de ce qu'on tape.
  Future<void> deverrouiller({
    required String phrase,
    bool parRecuperation = false,
  }) async {
    final generations = await api.obtenir<List<dynamic>>('v1/auth/zk-keys');
    final ouvertes = <String, ClesOuvertes>{};

    for (final brute in generations) {
      if (brute is! Map<String, dynamic>) continue;
      final enveloppe = parRecuperation
          ? brute['recovery_wrapped_private_key']
          : brute['wrapped_private_key'];
      final selEncode = parRecuperation ? brute['recovery_salt'] : brute['wrap_salt'];
      final organisation = brute['organization_id'];
      final publique = brute['public_key'];
      if (enveloppe is! String ||
          selEncode is! String ||
          organisation is! String ||
          publique is! String) {
        continue;
      }

      final Uint8List sel;
      try {
        sel = base64Decode(selEncode);
      } on FormatException {
        continue;
      }

      final String privee;
      try {
        final cle = await coeur.deriverCle(phrase: phrase, sel: sel);
        final octets = await coeur.dechiffrerSymetrique(cle: cle, blob: enveloppe);
        privee = utf8.decode(octets);
      } on Object {
        // Une enveloppe que cette phrase n'ouvre pas : c'est le cas courant quand on a
        // plusieurs organisations et qu'on tape la phrase de l'une d'elles.
        continue;
      }

      // Les générations d'une même organisation arrivent de la plus récente à la plus
      // ancienne : la première ouverte est la courante, les suivantes servent à lire ce
      // qui a été scellé avant une rotation.
      final deja = ouvertes[organisation];
      ouvertes[organisation] = deja == null
          ? ClesOuvertes(organisation: organisation, publique: publique, privee: privee)
          : deja.avecAnterieure(privee);
    }

    if (ouvertes.isEmpty) throw ErreurDAuth.phraseIncorrecte;
    _cles
      ..clear()
      ..addAll(ouvertes);
  }

  /// Scelle un contenu vers la clé publique **courante** de l'organisation.
  ///
  /// Toujours la courante, jamais une génération retirée : sceller avec une ancienne
  /// produirait un contenu que les membres n'ayant que la nouvelle ne pourraient pas
  /// ouvrir — et l'échec ne se verrait qu'à la lecture, chez quelqu'un d'autre.
  Future<String> sceller(
    List<int> clair, {
    required String organisation,
    String domaine = domaineGhostcal,
  }) async {
    final cles = _cles[organisation];
    if (cles == null) throw ErreurDAuth.coffreFerme;
    return coeur.scellerVers(publique: cles.publique, clair: clair, domaine: domaine);
  }

  /// Ouvre un contenu scellé, en essayant les générations dans l'ordre.
  ///
  /// Aucun blob ne porte d'identifiant de clé : c'est l'authentification du chiffre qui
  /// rejette les mauvaises. Essayer dans l'ordre n'est donc pas une approximation, c'est
  /// le protocole.
  ///
  /// Rend nul plutôt que de jeter : un contenu illisible doit s'**afficher** en disant
  /// qu'il l'est, jamais faire disparaître la ligne.
  Future<Uint8List?> ouvrir(
    String blob, {
    required String organisation,
    String domaine = domaineGhostcal,
  }) async {
    final cles = _cles[organisation];
    if (cles == null) return null;
    for (final privee in [cles.privee, ...cles.anterieures]) {
      try {
        return await coeur.ouvrirSceau(privee: privee, blob: blob, domaine: domaine);
      } on Object {
        continue;
      }
    }
    return null;
  }
}
