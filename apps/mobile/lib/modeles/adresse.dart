/// Ce qu'on accepte comme adresse de serveur.
///
/// Taper « ghostcal.stackops.ch » est le geste naturel ; le refuser au motif qu'il manque
/// « https:// » ferait échouer la toute première tentative de quelqu'un qui a pourtant
/// donné la bonne adresse.
///
/// Porté à l'identique de `AdresseDeServeur` côté Swift, avec ses vecteurs — y compris
/// l'exception de la boucle locale, où un serveur de développement tourne en clair, et le
/// refus d'un hôte distant en clair, où les jetons de session passeraient en lisible.
library;

class AdresseDeServeur {
  static Uri? normaliser(String saisie) {
    final texte = saisie.trim();
    if (texte.isEmpty) return null;

    final avecSchema = texte.contains('://')
        ? texte
        : '${_estBoucleLocale(texte) ? 'http' : 'https'}://$texte';

    final url = Uri.tryParse(avecSchema);
    if (url == null) return null;
    final schema = url.scheme.toLowerCase();
    if (schema != 'https' && schema != 'http') return null;
    if (url.host.isEmpty) return null;
    return url;
  }

  static bool _estBoucleLocale(String texte) {
    final hote = texte.split('/').first;
    final sansPort = hote.split(':').first;
    return const ['localhost', '127.0.0.1', '::1', '[::1]'].contains(sansPort.toLowerCase());
  }
}
