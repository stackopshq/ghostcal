import 'package:flutter/material.dart';

import '../services/biometrie.dart';
import '../services/session.dart';
import '../theme.dart';

/// Entrer dans GhostCal — **le même écran que le déverrouillage de GhostPass**, aux
/// couleurs et à la marque de GhostCal.
///
/// C'est délibéré et ça se copie structure par structure : enseigne sur plaque avec son
/// halo, titre, sous-titre, puis une carte de verre portant les champs et les actions. Les
/// deux applications sont des frères ; un écran d'entrée qui diverge fait douter qu'elles
/// viennent du même endroit, ce qui est exactement ce qu'un coffre chiffré ne peut pas se
/// permettre.
///
/// Trois visages, qui correspondent aux trois états de la session — et il faut qu'ils
/// soient distincts, sinon on redemande à quelqu'un ce qu'il vient de donner :
///
/// - **une session enregistrée** : la phrase seule, l'adresse et le compte étant connus ;
/// - **rien d'enregistré** : l'adresse, le compte, la phrase ;
/// - **connecté mais coffre fermé** : la phrase seule, avec la raison de l'échec précédent
///   affichée — c'est le cas le plus mal traité par les applications qui confondent « pas
///   authentifié » et « pas déchiffré ».
class EcranDeConnexion extends StatefulWidget {
  const EcranDeConnexion({super.key, required this.session});

  final Session session;

  @override
  State<EcranDeConnexion> createState() => _EcranDeConnexionState();
}

class _EcranDeConnexionState extends State<EcranDeConnexion> {
  late final _serveur = TextEditingController(text: widget.session.serveur);
  late final _email = TextEditingController(text: widget.session.email);
  final _phrase = TextEditingController();
  bool _parRecuperation = false;
  bool _changerDeCompte = false;
  bool _phraseVisible = false;

  final _biometrie = Biometrie();

  /// La biométrie de cet appareil, ou `null` s'il n'y en a pas d'utilisable.
  Empreinte? _empreinte;

  /// Une phrase est-elle déjà scellée ? C'est **cet** état, et non un réglage à part, qui
  /// dit si l'on peut ouvrir par le visage : un réglage séparé pourrait affirmer « activé »
  /// alors que l'entrée a été invalidée par un nouvel enrôlement, et le bouton ouvrirait
  /// alors une erreur au lieu du coffre.
  bool _scellee = false;

  /// Retenir la phrase après ce déverrouillage-ci. Proposé **pendant** la saisie : c'est le
  /// seul moment où le secret est sous la main, et le seul où l'on peut demander l'accord
  /// de celle qui le tape.
  bool _retenir = false;

  Session get session => widget.session;
  bool get _coffreFerme => session.etat == Etat.coffreFerme;
  bool get _reprise => session.sessionEnregistree && !_changerDeCompte;

  @override
  void initState() {
    super.initState();
    _regarderLaBiometrie();
  }

  Future<void> _regarderLaBiometrie() async {
    final empreinte = await _biometrie.disponible();
    // `aUnePhrase` interroge la présence, pas la valeur : demander la valeur ici ferait
    // surgir le visage à l'ouverture de l'écran, avant qu'on ait rien demandé.
    final scellee = empreinte == null ? false : await _biometrie.aUnePhrase();
    if (mounted) {
      setState(() {
        _empreinte = empreinte;
        _scellee = scellee;
      });
    }
  }

  /// Ouvre par le visage : on relit la phrase scellée et on suit le chemin ordinaire.
  ///
  /// Rien de particulier n'est tenté en cas de refus ou d'entrée invalidée — l'écran de
  /// saisie est déjà là, et c'est le repli juste.
  Future<void> _ouvrirParBiometrie() async {
    final phrase = await _biometrie.rappeler();
    if (phrase == null || !mounted) return;
    _phrase.text = phrase;
    await _valider();
  }

  @override
  void dispose() {
    _serveur.dispose();
    _email.dispose();
    _phrase.dispose();
    super.dispose();
  }

  Future<void> _valider() async {
    session
      ..serveur = _serveur.text
      ..email = _email.text;
    if (_coffreFerme) {
      await session.deverrouiller(
          phrase: _phrase.text, parRecuperation: _parRecuperation);
    } else if (_reprise) {
      await session.reprendre(phrase: _phrase.text, parRecuperation: _parRecuperation);
    } else {
      await session.seConnecter(motDePasse: _phrase.text);
    }
    // Seulement après coup : on ne scelle jamais une phrase qu'on n'a pas vue ouvrir le
    // coffre. La sceller avant vaudrait promesse d'un déverrouillage qui échouera.
    if (_retenir && session.etat == Etat.ouvert) {
      await _biometrie.retenir(_phrase.text);
    }
  }

  @override
  Widget build(BuildContext context) {
    return FondGhost(
      child: Scaffold(
        body: SafeArea(
          child: SingleChildScrollView(
            // Le clavier couvre le bas de la carte. Faire défiler le referme ; un
            // appui dans le vide, non.
            keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
            child: Center(
              child: ConstrainedBox(
                // La même largeur que GhostPass : au-delà, sur iPad, les champs
                // s'étirent sur toute la dalle et le formulaire perd sa forme.
                constraints: const BoxConstraints(maxWidth: 420),
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 40),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [_enseigne(), const SizedBox(height: 24), _carte()],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _enseigne() {
    final gc = Gc.of(context);
    return Column(
      children: [
        // La marque est sur fond transparent : posée à même l'écran, elle flotterait.
        // Une plaque franchement noire ou franchement blanche la détache — pas une
        // surface du thème, qui la ferait se fondre à nouveau.
        DecoratedBox(
          decoration: BoxDecoration(
            color: gc.sombre ? Colors.black : Colors.white,
            borderRadius: BorderRadius.circular(22),
            border: Border.all(color: gc.bordure),
            // La marque rayonne : c'est le seul néon de cet écran, et c'est ce qui
            // rattache GhostCal au reste de la suite.
            boxShadow: gc.halo(1),
          ),
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Image.asset('assets/marque/logo.png', width: 64, height: 64),
          ),
        ),
        const SizedBox(height: 10),
        Text(
          'GhostCal',
          style: TextStyle(
            fontSize: 28,
            fontWeight: FontWeight.bold,
            color: gc.encre,
          ),
        ),
        const SizedBox(height: 2),
        Text(
          _reprise || _coffreFerme
              ? 'Coffre enregistré sur cet appareil'
              : 'Agenda chiffré de bout en bout',
          style: TextStyle(fontSize: 13, color: gc.estompe),
        ),
      ],
    );
  }

  Widget _carte() {
    final gc = Gc.of(context);
    return CarteDeVerre(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ..._champs(gc),
          if (session.erreur != null) ...[
            const SizedBox(height: 18),
            _avertissement(gc.danger, Icons.warning_amber_rounded, session.erreur!),
          ],
          const SizedBox(height: 18),
          BoutonPrincipal(
            onPressed: session.occupe || _phrase.text.isEmpty ? null : _valider,
            child: session.occupe
                ? const SizedBox(
                    height: 18,
                    width: 18,
                    child: CircularProgressIndicator(
                        strokeWidth: 2, color: Gc.surAccent))
                : Text(_coffreFerme || _reprise ? 'Déverrouiller' : 'Se connecter'),
          ),
          ..._biometrique(gc),
          ..._liens(gc),
        ],
      ),
    );
  }

  /// Le bouton d'ouverture par le visage, ou la proposition de retenir la phrase.
  ///
  /// Jamais les deux, et jamais sur une première connexion : il n'y a de sens à ouvrir par
  /// le visage que devant un coffre déjà connu de cet appareil.
  List<Widget> _biometrique(Gc gc) {
    final empreinte = _empreinte;
    if (empreinte == null || !(_coffreFerme || _reprise)) return const [];

    if (_scellee) {
      return [
        const SizedBox(height: 12),
        // L'icône seule, comme sur GhostPass iOS : le geste attendu se reconnaît à son
        // dessin plus vite qu'il ne se lit. Le nom reste en étiquette de sémantique —
        // c'est une **action**, et sans elle un lecteur d'écran annoncerait « bouton »
        // sans dire lequel.
        Semantics(
          label: 'Ouvrir avec ${empreinte.nom}',
          button: true,
          child: OutlinedButton(
            onPressed: session.occupe ? null : _ouvrirParBiometrie,
            style: OutlinedButton.styleFrom(
              minimumSize: const Size.fromHeight(48),
              side: BorderSide(color: gc.bordureFranche),
              foregroundColor: gc.accentTexte,
            ),
            child: Icon(empreinte.icone, size: 24),
          ),
        ),
      ];
    }

    return [
      const SizedBox(height: 4),
      CheckboxListTile(
        value: _retenir,
        onChanged: (v) => setState(() => _retenir = v ?? false),
        contentPadding: EdgeInsets.zero,
        controlAffinity: ListTileControlAffinity.leading,
        dense: true,
        title: Text(
          'Ouvrir avec ${empreinte.nom}',
          style: TextStyle(color: gc.encre, fontSize: 14),
        ),
        subtitle: Text(
          'La phrase est scellée sur cet appareil, relisible par ${empreinte.nom} seul.',
          style: TextStyle(color: gc.estompe, fontSize: 12),
        ),
      ),
    ];
  }

  List<Widget> _champs(Gc gc) {
    if (_coffreFerme) {
      return [
        // Le coffre est fermé mais la session est ouverte : le dire, plutôt que de
        // renvoyer à un formulaire de connexion qui laisserait croire au contraire.
        _avertissement(
          gc.estompe,
          Icons.lock_outline,
          'Vous êtes connecté, mais le coffre est resté fermé : '
          '${session.raisonDuCoffre ?? "cette phrase ne l'ouvre pas."}',
        ),
        const SizedBox(height: 18),
        _champDePhrase(gc),
      ];
    }
    if (_reprise) {
      return [
        _champ(gc, 'Compte', enfant: _valeurFigee(gc, session.email)),
        const SizedBox(height: 18),
        _champDePhrase(gc),
      ];
    }
    return [
      _champ(
        gc,
        'Serveur',
        controleur: _serveur,
        cle: const Key('champ.serveur'),
        // Le domaine est celui que la RFC 2606 réserve aux exemples — il ne résout
        // nulle part, donc personne ne se connectera par mégarde chez un tiers.
        indice: 'https://ghostcal.example.com',
        clavier: TextInputType.url,
      ),
      const SizedBox(height: 18),
      _champ(gc, 'Adresse e-mail',
          controleur: _email,
          cle: const Key('champ.email'),
          indice: 'vous@exemple.ch',
          clavier: TextInputType.emailAddress),
      const SizedBox(height: 18),
      _champDePhrase(gc),
    ];
  }

  List<Widget> _liens(Gc gc) {
    final liens = <Widget>[
      // La phrase de récupération n'a de sens qu'au déverrouillage : à la connexion,
      // c'est le mot de passe du compte qu'on tape, et ils ne s'échangent pas.
      if (_coffreFerme || _reprise)
        _lien(
          gc,
          _parRecuperation
              ? 'Utiliser mon mot de passe'
              : 'Utiliser ma phrase de récupération',
          () => setState(() => _parRecuperation = !_parRecuperation),
        ),
      if (_reprise)
        _lien(gc, 'Utiliser un autre compte', () {
          setState(() {
            _changerDeCompte = true;
            _parRecuperation = false;
            _phrase.clear();
          });
        }),
    ];
    return liens.isEmpty
        ? const []
        : [const SizedBox(height: 10), ...liens];
  }

  Widget _lien(Gc gc, String texte, VoidCallback action) => Align(
        alignment: Alignment.center,
        child: TextButton(
          onPressed: action,
          style: TextButton.styleFrom(
            foregroundColor: gc.accentTexte,
            textStyle: const TextStyle(fontSize: 13),
            minimumSize: const Size(0, 36),
          ),
          child: Text(texte),
        ),
      );

  Widget _avertissement(Color teinte, IconData icone, String texte) => Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icone, size: 16, color: teinte),
          const SizedBox(width: 8),
          Expanded(
            child: Text(texte, style: TextStyle(fontSize: 13, color: teinte)),
          ),
        ],
      );

  /// Le libellé de section de la charte : petites capitales espacées, teinte estompée.
  /// Il nomme sans se disputer l'attention avec ce qu'on saisit.
  Widget _libelle(Gc gc, String texte) => Text(
        texte.toUpperCase(),
        style: TextStyle(
          color: gc.estompe,
          fontSize: 11,
          fontWeight: FontWeight.w600,
          letterSpacing: 1.1,
        ),
      );

  Widget _champ(
    Gc gc,
    String titre, {
    TextEditingController? controleur,
    Widget? enfant,
    Key? cle,
    String? indice,
    TextInputType? clavier,
  }) =>
      Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _libelle(gc, titre),
          const SizedBox(height: 7),
          enfant ??
              TextField(
                key: cle,
                controller: controleur,
                keyboardType: clavier,
                autocorrect: false,
                enableSuggestions: false,
                textCapitalization: TextCapitalization.none,
                decoration: InputDecoration(hintText: indice),
              ),
        ],
      );

  /// Le compte d'une session enregistrée : montré, pas modifiable. Le rendre saisissable
  /// laisserait croire qu'on peut changer de compte sans repasser par la connexion.
  Widget _valeurFigee(Gc gc, String texte) => Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
        decoration: BoxDecoration(
          color: gc.surface2,
          borderRadius: BorderRadius.circular(Mesures.rayon),
          border: Border.all(color: gc.bordure),
        ),
        child: Text(texte, style: TextStyle(color: gc.estompe)),
      );

  Widget _champDePhrase(Gc gc) => _champ(
        gc,
        _parRecuperation ? 'Phrase de récupération' : 'Mot de passe maître',
        enfant: TextField(
          key: const Key('champ.phrase'),
          controller: _phrase,
          obscureText: !_phraseVisible,
          autocorrect: false,
          enableSuggestions: false,
          // Le bouton dépend du champ : sans cela, il resterait éteint jusqu'à ce
          // qu'autre chose provoque un rafraîchissement.
          onChanged: (_) => setState(() {}),
          onSubmitted: (_) => _valider(),
          decoration: InputDecoration(
            hintText: 'Votre mot de passe',
            suffixIcon: IconButton(
              icon: Icon(_phraseVisible ? Icons.visibility_off : Icons.visibility),
              // Une phrase de récupération fait douze mots : la taper à l'aveugle
              // garantit la faute de frappe, et l'erreur rendue ne dit pas où.
              tooltip: _phraseVisible ? 'Masquer' : 'Afficher',
              onPressed: () => setState(() => _phraseVisible = !_phraseVisible),
            ),
          ),
        ),
      );
}
