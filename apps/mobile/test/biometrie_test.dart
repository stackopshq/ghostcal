import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/l10n/generated/app_localisations.dart';
import 'package:ghostcal/services/biometrie.dart';
import 'package:ghostcal/services/trousseau.dart';

/// Ce que ces témoins gardent, et ce qu'ils ne peuvent pas garder.
///
/// Ils vérifient les **contraintes déclarées au magasin** — celles qui décident si la
/// phrase est scellée derrière le matériel ou simplement rangée. C'est vérifiable ici
/// parce que le paquet sérialise ses options ; la seule alternative serait un appareil
/// physique avec un visage enrôlé, et un désenrôlement au milieu du test.
///
/// Ce qu'ils **ne prouvent pas** : que l'appareil honore ces contraintes. Aucun test hors
/// matériel ne le peut, et c'est `integration_test/biometrie_trois_etats_test.dart` qui
/// s'en charge — il a relevé, le 2026-09-26 sur iPhone 17 Pro, 4 ms pour une entrée sans
/// contrôle contre 45 174 ms pour la même sous `biometryCurrentSet`. La porte existe.
///
/// Sur Android, l'invalidation à l'enrôlement d'un nouveau visage reste à confirmer sur
/// le Redmi ; côté GhostPass, elle l'a été.
void main() {
  group('les contraintes du magasin biométrique', () {
    final android = Biometrie.magasin().aOptions.toMap();
    final apple = Biometrie.magasin().iOptions.params;

    /// Le témoin le plus important du fichier.
    ///
    /// Le défaut du paquet est `biometricOrDeviceCredential`, et il **désarme la
    /// garantie** : accepter le code de l'appareil rend `setInvalidatedByBiometricEnrollment`
    /// sans effet, puisqu'un visage nouvellement enrôlé n'invalide plus rien si le code
    /// suffit à ouvrir. C'est la correction qu'a dû recevoir l'ADR-0002 de GhostPass, et
    /// c'est exactement le genre de réglage qu'une montée de version reprend en silence.
    test('Android n\'accepte que la biométrie forte, jamais le code de l\'appareil', () {
      expect(android['biometricType'], 'strongBiometricOnly');
      expect(android['enforceBiometrics'], 'true');
    });

    /// `biometryAny` laisserait quelqu'un qui a le code ajouter son propre visage et
    /// ouvrir le coffre. `biometryCurrentSet` invalide l'entrée au nouvel enrôlement.
    test('Apple lie l\'entrée aux biométries actuellement enrôlées', () {
      expect(apple['accessControlFlags'], contains('biometryCurrentSet'));
      // `passcode` est `kSecAttrAccessibleWhenPasscodeSetThisDeviceOnly` : pas de code
      // posé, pas d'entrée ; et jamais transférée vers un autre appareil.
      expect(apple['accessibility'], 'passcode');
    });

    /// Sans cloisonnement, la contrainte biométrique s'appliquerait aussi aux jetons de
    /// session : rouvrir l'application demanderait le visage pour lire une valeur qui n'a
    /// pas à être protégée ainsi, et le coffre deviendrait pénible sans être plus sûr.
    test('le magasin biométrique est séparé de celui des jetons', () {
      expect(android['storageNamespace'], isNotEmpty);
      expect(apple['accountName'], isNotNull);

      final jetons = Trousseau.magasin;
      expect(
        jetons.aOptions.toMap()['storageNamespace'],
        isNot(android['storageNamespace']),
        reason: 'les deux magasins partageraient leurs contraintes',
      );
      expect(
        jetons.iOptions.params['accessControlFlags'],
        isNull,
        reason: 'les jetons ne doivent jamais exiger le visage',
      );
    });

    /// La 11 met `resetOnError` à **vrai** par défaut : une simple erreur de lecture
    /// efface tout le magasin. Sur celui des jetons, cela déconnecte sans un mot ; ici,
    /// cela perdrait la phrase scellée sans que rien ne le dise.
    test('une erreur de lecture n\'efface pas le magasin', () {
      expect(android['resetOnError'], 'false');
      expect(Trousseau.magasin.aOptions.toMap()['resetOnError'], 'false');
    });
  });

  /// **L'interrogation de présence doit être muette, et rien d'autre ne le dit.**
  ///
  /// Le défaut mesuré le 2026-09-26 sur iPhone 17 Pro : `sceau()` présentait Face ID —
  /// 29 425 ms, contre 0 ms pour la même question sur une entrée sans contrôle d'accès.
  /// Ouvrir les réglages demandait donc un visage pour afficher une ligne d'état.
  ///
  /// Ce témoin ne prouve pas que l'invite a disparu : seul l'appareil peut le dire, et
  /// `integration_test/biometrie_trois_etats_test.dart` s'en charge. Il garde la chose
  /// qui, elle, se perd en silence — que le drapeau soit **posé sur le bon magasin** et
  /// sur lui seul. L'oublier ne casse aucune compilation.
  group('la question de présence ne présente rien', () {
    test('le magasin muet porte kSecUseAuthenticationUIFail', () {
      final muet = Biometrie.magasin(null, true).iOptions.params;
      expect(muet['authenticationUIBehavior'], 'u_AuthUIF',
          reason: 'la valeur littérale de la constante Security.framework, relevée le '
              '2026-09-26 : une faute de frappe ici ramène l\'invite sans rien casser');
    });

    /// Et l'inverse : la **lecture** doit continuer à présenter l'invite. Poser le drapeau
    /// partout ferait échouer tout déverrouillage biométrique — la fonction entière
    /// rendrait `errSecInteractionNotAllowed`, c'est-à-dire « pas maintenant », pour
    /// toujours.
    test('le magasin de lecture, lui, laisse l\'invite paraître', () {
      final lecture = Biometrie.magasin().iOptions.params;
      expect(lecture['authenticationUIBehavior'], isNull);
    });

    /// Les deux magasins ne diffèrent que par ce drapeau : s'ils divergeaient sur le
    /// cloisonnement ou l'accessibilité, la présence interrogerait une **autre** entrée
    /// que celle qu'on lit, et répondrait juste sur la mauvaise.
    test('muet ou non, c\'est la même entrée qu\'on interroge', () {
      final muet = Map.of(Biometrie.magasin(null, true).iOptions.params)
        ..remove('authenticationUIBehavior');
      final lecture = Map.of(Biometrie.magasin().iOptions.params)
        ..remove('authenticationUIBehavior');
      expect(muet, lecture);
    });
  });

  /// L'icône suit le matériel. Une icône Face ID en dur mentirait sur un téléphone à
  /// empreinte — c'est la raison d'être de cette énumération.
  test('chaque empreinte porte son propre dessin', () {
    final icones = Empreinte.values.map((e) => e.icone).toSet();
    expect(icones.length, Empreinte.values.length,
        reason: 'deux biométries différentes ne peuvent pas montrer le même dessin');
  });

  group('les libellés de l\'invite Android suivent la langue', () {
    /// **Le défaut réparé le 2026-09-26.** Les trois chaînes étaient écrites en français
    /// dans un `static const`, et le `BiometricPrompt` d'Android les affichait telles
    /// quelles à tout le monde. Deux des clés existaient pourtant déjà dans les `.arb` :
    /// elles avaient été traduites, puis jamais branchées, et rien ne le signalait.
    test('les trois chaînes viennent des traductions, pas du code', () async {
      for (final locale in L.supportedLocales) {
        final l = await L.delegate.load(locale);
        final options = Biometrie.magasin(InvitesBiometriques.depuis(l))
            .aOptions
            .toMap();
        expect(options['biometricPromptTitle'], l.ouvrirLeCoffre);
        expect(options['biometricPromptNegativeButton'], l.utiliserLaPhrase);
        // Le nom du produit, verbatim : il ne se traduit pas.
        expect(options['biometricPromptSubtitle'], 'GhostCal');
      }
    });

    /// Sans invites posées, c'est le défaut **du paquet** qui s'applique —
    /// « Authenticate to access », relevé et non supposé. Ce n'est pas idéal, mais un
    /// libellé générique anglais se reconnaît comme tel ; du français servi à un
    /// anglophone se lit comme un produit cassé. Le témoin garde la seule chose qui
    /// compte : que ce ne soient plus **nos** chaînes françaises.
    test('sans invites posées, ce n\'est plus du français en dur', () async {
      final fr = await L.delegate.load(const Locale('fr'));
      final options = Biometrie.magasin().aOptions.toMap();
      expect(options['biometricPromptTitle'], isNot(fr.ouvrirLeCoffre));
      expect(options['biometricPromptNegativeButton'], isNot(fr.utiliserLaPhrase));
    });

    /// **La faute exacte de GhostPass iOS, gardée ici.** Un `nom` français en dur sur
    /// l'énumération donnait « Open with la biométrie » sur une interface anglaise.
    /// « Face ID » et « Touch ID », eux, ne se traduisent pas : ce sont des marques.
    test('le repli générique se traduit, les marques d\'Apple non', () async {
      final fr = await L.delegate.load(const Locale('fr'));
      final en = await L.delegate.load(const Locale('en'));

      expect(Empreinte.visage.nom(fr), 'Face ID');
      expect(Empreinte.visage.nom(en), 'Face ID');
      expect(Empreinte.doigt.nom(fr), 'Touch ID');

      expect(Empreinte.autre.nom(fr), fr.laBiometrie);
      expect(Empreinte.autre.nom(en), en.laBiometrie);
      expect(Empreinte.autre.nom(en), isNot(Empreinte.autre.nom(fr)),
          reason: 'le repli générique est resté dans une seule langue');
    });
  });
}
