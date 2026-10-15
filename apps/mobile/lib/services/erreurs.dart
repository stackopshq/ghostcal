import 'dart:async';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../l10n/generated/app_localisations.dart';
import 'api.dart';
import 'auth.dart';

/// The server could not be reached at all: no network, wrong address, TLS failure,
/// or no answer in time. Raised by [ClientAPI] instead of the transport's own
/// exception, whose text ("ClientException with SocketException: Connection refused
/// (OS Error…") was shown verbatim to users.
class ErreurReseau implements Exception {
  const ErreurReseau(this.genre, [this.cause]);

  final GenreDErreurReseau genre;

  /// The transport exception, kept for logs and tests; never shown.
  final Object? cause;

  /// Classifies a transport exception, or returns `null` if [e] is not one.
  static ErreurReseau? depuis(Object e) => switch (e) {
        TimeoutException() => ErreurReseau(GenreDErreurReseau.delai, e),
        HandshakeException() || TlsException() =>
          ErreurReseau(GenreDErreurReseau.certificat, e),
        SocketException() || http.ClientException() =>
          ErreurReseau(GenreDErreurReseau.injoignable, e),
        _ => null,
      };

  @override
  String toString() => 'ErreurReseau($genre): $cause';
}

enum GenreDErreurReseau { injoignable, delai, certificat }

/// The server address typed on the sign-in screen does not parse.
class AdresseInvalide implements Exception {
  const AdresseInvalide();
}

/// The saved session was refused by the server; the user must sign in again.
class SessionExpiree implements Exception {
  const SessionExpiree();
}

/// The sentence a user reads for [e], in the screen's language.
///
/// Every screen used to show `'$e'`, which put Dart and Java class names on screen.
/// [connexion] is true on the sign-in form, where a 401 means wrong credentials
/// rather than an expired session.
String lisible(Object e, L l, {bool connexion = false}) => switch (e) {
      ErreurReseau(genre: GenreDErreurReseau.injoignable) => l.erreurServeurInjoignable,
      ErreurReseau(genre: GenreDErreurReseau.delai) => l.erreurServeurLent,
      ErreurReseau(genre: GenreDErreurReseau.certificat) => l.erreurCertificat,
      AdresseInvalide() => l.erreurAdresseInvalide,
      SessionExpiree() => l.erreurSessionExpiree,
      ErreurDAuth() when identical(e, ErreurDAuth.phraseIncorrecte) =>
        l.erreurPhraseIncorrecte,
      ErreurDAuth() when identical(e, ErreurDAuth.coffreFerme) =>
        l.coffreFermeChiffrementImpossible,
      ErreurAPI(statut: 401) =>
        connexion ? l.erreurIdentifiants : l.erreurSessionExpiree,
      ErreurAPI(statut: 429) => l.erreurTropDEssais,
      ErreurAPI(statut: >= 500) => l.erreurServeur,
      // A 4xx the server explained: its sentence is more precise than any we could
      // write here, even though the server speaks English only.
      ErreurAPI(:final message) when message.isNotEmpty => message,
      ErreurAPI(:final statut) => l.erreurStatut(statut),
      _ => l.erreurInattendue,
    };
