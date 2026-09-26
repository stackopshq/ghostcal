// Ce que le **vrai** trousseau répond — relevé sur matériel, pas déduit.
//
// ─── Ce que les témoins hors matériel ne peuvent pas dire ───
//
// `test/biometrie_test.dart` lit les options **déclarées** au magasin.
// `test/biometrie_auto_test.dart` éprouve ce que l'écran fait de chaque `Issue`, avec un
// magasin feint. Les deux sont utiles et partagent le même angle mort : ils ne disent rien
// de ce que la plateforme fait de ce qu'on lui a demandé. Un trousseau qui ignorerait
// `biometryCurrentSet` les laisserait tous les deux au vert, et la phrase serait
// simplement **rangée** derrière une invite décorative.
//
// ─── Le piège de mesure qui a failli faire conclure l'inverse ───
//
// Le premier jet de ce fichier affirmait : « personne ne présente de visage, donc la
// lecture doit échouer ». Relevé sur l'iPhone 17 Pro le 2026-09-26, elle a **réussi** en
// 4 secondes, et le témoin a crié que la garantie ne tenait pas.
//
// Elle tenait. Face ID s'était présenté et **avait reconnu quelqu'un** : le téléphone est
// posé sur un bureau, face à la personne qui lance le test. « Personne ne regarde »
// n'est pas une hypothèse qu'un test peut tenir ; c'est une hypothèse sur la pièce.
//
// Ce qui se mesure, en revanche, c'est **le passage par la porte**. Une entrée sans
// contrôle d'accès se relit en 1 ms ; la même sous `passcode + biometryCurrentSet` a
// demandé 6 941 ms, le temps que l'invite s'affiche et qu'un visage y réponde. Trois
// ordres de grandeur, sur le même appareil, dans la même exécution. Ce fichier compare
// donc la lecture scellée à un **témoin négatif** écrit à côté d'elle, plutôt qu'à une
// constante — un seuil en dur mesurerait la vitesse du téléphone.
//
// ─── Ce qu'il n'atteint pas, et qu'il ne faut pas compter couvert ───
//
// - **le refus** : demande que quelqu'un écarte l'invite. Un test sans surveillance ne
//   peut pas le provoquer, et le laisser s'obtenir « par expiration » le confondrait avec
//   une panne ;
// - **« pas maintenant »** (`errSecInteractionNotAllowed`) : demande que l'application ne
//   soit pas au premier plan, ou que l'appareil soit verrouillé. Un test d'intégration est
//   au premier plan par construction. **Ce cas-là reste éprouvé uniquement par
//   `test/biometrie_auto_test.dart`**, qui peut le feindre — et c'est précisément celui
//   qui est passé au travers chez GhostPass le 2026-09-25. Le dire vaut mieux que de
//   laisser croire que le matériel l'a vu.

import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/services/biometrie.dart';
import 'package:integration_test/integration_test.dart';

const temoin = 'phrase-temoin-des-trois-etats-2026';

/// Un magasin **sans** contrainte biométrique, écrit à côté du vrai. C'est la ligne de
/// base : ce que coûte une lecture du trousseau quand aucune porte ne la garde.
const nu = FlutterSecureStorage(
  iOptions: IOSOptions(
    accountName: 'ghostcal.temoin-negatif',
    accessibility: KeychainAccessibility.unlocked_this_device,
  ),
);

void dire(String ligne) => debugPrint('TROIS-ETATS: $ligne');

/// Combien de temps met une lecture, en millisecondes.
Future<(int, T)> chronometrer<T>(Future<T> Function() corps) async {
  final debut = DateTime.now();
  final valeur = await corps();
  return (DateTime.now().difference(debut).inMilliseconds, valeur);
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  final biometrie = Biometrie();

  testWidgets('la plateforme expose une biométrie, et on sait laquelle', (tester) async {
    final empreinte = await biometrie.disponible();
    dire('disponible = ${empreinte?.name}');
    // Sur un iPhone sans `NSFaceIDUsageDescription`, `canCheckBiometrics` échoue et ceci
    // rend `null` : le bouton ne paraîtrait jamais sur un appareil pourtant équipé. Le
    // symptôme ne ressemble pas à une permission manquante, il ressemble à un téléphone
    // sans Face ID — d'où ce relevé, qui les distingue.
    expect(empreinte, isNotNull,
        reason: 'aucune biométrie vue : clé Info.plist manquante, ou rien d\'enrôlé');
  });

  /// **Le cas du milieu de la charte** : `errSecItemNotFound`, « l'enrôlement a disparu ».
  /// Aucun geste n'est requis pour le provoquer, et c'est celui que GhostPass a tu.
  testWidgets('rien de scellé se dit « absente », et jamais « échec »', (tester) async {
    await biometrie.oublier();

    final presence = await biometrie.sceau();
    dire('sceau() sur magasin vide = ${presence.name}');
    expect(presence, Issue.absente,
        reason: 'un magasin vide doit se lire « absent », pas « je ne sais pas »');

    final lecture = await biometrie.rappeler();
    dire('rappeler() sur magasin vide = ${lecture.issue.name} détail=${lecture.detail}');
    expect(lecture.issue, Issue.absente);
    expect(lecture.phrase, isNull);
  });

  /// L'écriture ne demande **pas** le visage : seule la lecture le fait. Si ce n'était pas
  /// vrai, proposer de retenir la phrase ouvrirait une invite au milieu d'un
  /// déverrouillage qui vient de réussir.
  ///
  /// Et la présence se lit sans invite non plus — sinon, savoir s'il faut afficher le
  /// bouton demanderait un visage avant qu'on ait rien demandé.
  testWidgets(
    'sceller et lire la présence ne demandent pas de visage',
    timeout: const Timeout(Duration(minutes: 5)),
    (tester) async {
      final (msEcriture, pose) = await chronometrer(() => biometrie.retenir(temoin));
      dire('retenir() = $pose en $msEcriture ms');
      expect(pose, isTrue, reason: 'le sceau n\'a pas pu être posé du tout');

      // La ligne de base : une interrogation de présence sur un magasin **sans** contrôle
      // d'accès. Ce que coûte la question quand aucune porte ne la garde.
      await nu.write(key: 'presence', value: temoin);
      final (msNu, _) = await chronometrer(() => nu.containsKey(key: 'presence'));
      dire('LIGNE DE BASE — containsKey sans contrôle = $msNu ms');

      final (msPresence, presence) = await chronometrer(biometrie.sceau);
      dire('sceau() sur entrée scellée = ${presence.name} en $msPresence ms');
      expect(presence, Issue.ouverte);

      // **Ce que ce témoin garde vraiment.** `sceau()` décide s'il faut afficher le
      // bouton, et il est appelé à l'ouverture de l'écran d'entrée **et** de celui des
      // réglages. S'il déclenchait le matériel, changer un délai de verrouillage ferait
      // surgir Face ID — ce qui apprend à écarter l'invite par réflexe, et rend la
      // biométrie moins sûre qu'elle ne l'était sans.
      //
      // Le seuil est large et relatif à la machine, pas à une constante : une invite
      // biométrique se compte en secondes, une simple interrogation de présence en
      // millisecondes. Relevé le 2026-09-26 sur iPhone 17 Pro : la lecture **avec**
      // invite a coûté 45 174 ms dans la même exécution.
      expect(msPresence, lessThan(2000),
          reason: 'l\'interrogation de présence a coûté $msPresence ms contre $msNu ms '
              'pour la même question sans contrôle : elle a probablement présenté une '
              'invite, et l\'écran des réglages demandera un visage pour rien');

      await nu.delete(key: 'presence');
    },
  );

  /// **La garantie elle-même**, et la seule chose que seul le matériel peut dire.
  ///
  /// On ne vérifie pas que la phrase se relit — ça, un fichier texte le ferait aussi. On
  /// vérifie qu'elle ne se relit **pas par le même chemin** qu'une valeur ordinaire : la
  /// lecture scellée doit coûter l'invite, la lecture nue ne doit rien coûter.
  ///
  /// Le facteur dix est volontairement large. Mesuré le 2026-09-26 sur iPhone 17 Pro :
  /// 1 ms pour le témoin nu, 6 941 ms pour l'entrée scellée — un facteur de près de
  /// sept mille. Un seuil serré rougirait sur un appareil lent sans rien apprendre ;
  /// celui-ci ne rougit que si la porte a disparu.
  testWidgets(
    'la phrase scellée passe par une porte que la phrase nue ne passe pas',
    timeout: const Timeout(Duration(minutes: 5)),
    (tester) async {
      await nu.write(key: 'ligne-de-base', value: temoin);
      final (msNu, valeurNue) = await chronometrer(() => nu.read(key: 'ligne-de-base'));
      dire('LIGNE DE BASE — lecture sans contrôle = $msNu ms');
      expect(valeurNue, temoin, reason: 'le témoin négatif n\'a rien relu : mesure nulle');

      await biometrie.retenir(temoin);
      final (msScelle, lecture) = await chronometrer(biometrie.rappeler);
      dire('lecture scellée = ${lecture.issue.name} en $msScelle ms');

      // Si la lecture a abouti, c'est qu'un visage enrôlé a répondu — et alors la porte
      // doit s'être vue. Si elle n'a pas abouti, la porte s'est vue aussi : dans les deux
      // cas, ce qui serait faux est qu'elle se relise **aussi vite** que la valeur nue.
      expect(msScelle, greaterThan(msNu * 10 + 200),
          reason: 'LA GARANTIE NE TIENT PAS : la phrase scellée se relit au même prix '
              'qu\'une valeur ordinaire ($msScelle ms contre $msNu ms). Elle est rangée, '
              'pas scellée.');

      if (lecture.issue == Issue.ouverte) {
        dire('un visage a répondu — le cas vert est éprouvé');
        expect(lecture.phrase, temoin);
      } else {
        dire('aucun visage n\'a répondu — le cas vert N\'EST PAS éprouvé '
            'par cette exécution ; la porte, elle, l\'est');
      }

      await nu.delete(key: 'ligne-de-base');
    },
  );

  tearDownAll(() async {
    await biometrie.oublier();
    dire('magasin rendu à son état vide');
  });
}
