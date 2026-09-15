// La garantie du magasin scellé, éprouvée sur un vrai KeyStore.
//
// ─── Pourquoi ce fichier ne peut pas être un `flutter test` ───
//
// `test/biometrie_test.dart` vérifie les **options déclarées** — que `strongBiometricOnly`
// est demandé, que le magasin est cloisonné. C'est utile et c'est insuffisant : il vérifie
// ce qu'on a demandé à la plateforme, jamais ce qu'elle en fait. Un magasin qui ignorerait
// silencieusement `enforceBiometrics` passerait ces témoins au vert.
//
// ─── Pourquoi tout tient dans une seule exécution ───
//
// Le premier jet séparait « sceller » et « vérifier » en deux lancements, l'hôte modifiant
// l'enrôlement entre les deux. **Il ne prouvait rien** : `flutter test` désinstalle
// l'application à la fin de chaque exécution, donc la seconde relisait un magasin vide et
// concluait au vert. Vérifié après coup — `pm list packages` ne trouvait plus le paquet.
// C'est le défaut classique du témoin qui ne sait pas rougir : il aurait donné la même
// sortie si la garantie n'existait pas du tout.
//
// Tout se passe donc dans une seule installation : on scelle, on relit pour prouver que
// c'était lisible, on **attend** que l'hôte enrôle une nouvelle empreinte, puis on relit.
//
// ─── Ce que l'hôte doit faire pendant l'attente ───
//
// Enrôler une empreinte de plus, par l'interface des Réglages — le HAL « ranchu » de
// l'émulateur n'expose aucune commande d'enrôlement. Voir `tools/android/enroler.sh`.

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/services/biometrie.dart';
import 'package:integration_test/integration_test.dart';

const temoin = 'phrase-temoin-du-banc-2026';

/// De quoi laisser l'hôte faire son travail d'enrôlement.
const attente = Duration(seconds: 150);

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  final biometrie = Biometrie();

  testWidgets(
    'un nouvel enrôlement rend la phrase scellée illisible',
    timeout: const Timeout(Duration(minutes: 6)),
    (tester) async {
      // ─── 1. Sceller ───
      await biometrie.oublier();
      await biometrie.retenir(temoin);
      expect(await biometrie.sceau() == Issue.ouverte, isTrue,
          reason: 'la phrase n\'a pas été scellée du tout');

      // ─── 2. Prouver que c'était lisible ───
      //
      // Sans cette étape, un échec en 4 se confondrait avec « ça n'a jamais marché », et
      // le fichier entier ne dirait rien.
      final avant = await biometrie.rappeler();
      expect(avant.issue, Issue.ouverte,
          reason: 'le témoin ne se relit pas avant même le changement d\'enrôlement : '
              'inutile d\'aller plus loin');
      expect(avant.phrase, temoin);

      // ─── 3. Laisser l'hôte enrôler une nouvelle empreinte ───
      debugPrint('TEMOIN: scellé et relu — enrôlez maintenant');
      await Future<void>.delayed(attente);

      // ─── 4. La seule étape qui prouve quelque chose ───
      //
      // Acceptable : l'entrée a disparu, ou elle se signale invalidée. Les deux disent que
      // la clé est morte avec l'ancien enrôlement.
      //
      // Inacceptable : que la phrase se relise. Ce serait une valeur simplement rangée
      // derrière une invite décorative — exactement ce que cette architecture prétend
      // empêcher, et ce que personne n'avait encore constaté dans un sens ou dans l'autre.
      //
      // **L'hôte doit continuer à poser un doigt enrôlé pendant cette lecture-ci.** Sans
      // cela, une garantie qui ne tiendrait pas ouvrirait une invite que personne
      // n'honore, la lecture échouerait sur un délai, et ce témoin conclurait au vert
      // pour la mauvaise raison. Le piège va dans le sens de ce qu'on espère, ce qui le
      // rend particulièrement facile à ne pas voir.
      final apres = await biometrie.rappeler();
      debugPrint('TEMOIN: après enrôlement, issue = ${apres.issue}');
      expect(
        apres.issue,
        isNot(Issue.ouverte),
        reason: 'LA GARANTIE NE TIENT PAS : la phrase se relit encore après '
            'l\'enrôlement d\'une nouvelle empreinte. Elle est rangée, pas scellée.',
      );
      expect(apres.phrase, isNull);
    },
  );
}
