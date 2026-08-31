import 'package:flutter/material.dart';

import '../services/session.dart';
import '../theme.dart';

/// Entrer dans GhostCal.
///
/// L'écran a trois visages, qui correspondent aux trois états de la session — et il faut
/// qu'ils soient distincts, sinon on redemande à quelqu'un ce qu'il vient de donner :
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

  Session get session => widget.session;
  bool get _coffreFerme => session.etat == Etat.coffreFerme;
  bool get _reprise => session.sessionEnregistree && !_changerDeCompte;

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
  }

  @override
  Widget build(BuildContext context) {
    final gc = Gc.of(context);
    return Scaffold(
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(20, 24, 20, 20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('GhostCal',
                  style: Theme.of(context)
                      .textTheme
                      .displaySmall
                      ?.copyWith(fontWeight: FontWeight.bold, color: gc.encre)),
              const SizedBox(height: 6),
              Text('Votre agenda, chiffré de bout en bout.',
                  style: TextStyle(color: gc.estompe)),
              const SizedBox(height: 22),
              ..._visage(gc),
              if (session.erreur != null) ...[
                const SizedBox(height: 14),
                Text(session.erreur!, style: TextStyle(color: gc.danger, fontSize: 13)),
              ],
              const SizedBox(height: 20),
              SizedBox(
                width: double.infinity,
                child: FilledButton(
                  onPressed: session.occupe ? null : _valider,
                  child: session.occupe
                      ? const SizedBox(
                          height: 18,
                          width: 18,
                          child: CircularProgressIndicator(strokeWidth: 2))
                      : Text(_coffreFerme || _reprise ? 'Déverrouiller' : 'Se connecter'),
                ),
              ),
              const SizedBox(height: 10),
              ..._bascules(gc),
            ],
          ),
        ),
      ),
    );
  }

  List<Widget> _visage(Gc gc) {
    if (_coffreFerme) {
      return [
        _encart(
          gc,
          'Vous êtes connecté, mais le coffre est resté fermé : '
          '${session.raisonDuCoffre ?? "cette phrase n'ouvre pas le coffre."}',
        ),
        const SizedBox(height: 14),
        _champDePhrase(),
      ];
    }
    if (_reprise) {
      return [
        Text('Session enregistrée pour ${session.email}',
            style: TextStyle(color: gc.estompe, fontSize: 13)),
        const SizedBox(height: 14),
        _champDePhrase(),
      ];
    }
    return [
      _champ(
        'Serveur',
        _serveur,
        // Le domaine est celui que la RFC 2606 réserve aux exemples — il ne résout nulle
        // part, donc personne ne se connectera par mégarde à l'instance d'un tiers.
        indice: 'https://ghostcal.example.com',
        clavier: TextInputType.url,
      ),
      const SizedBox(height: 12),
      _champ('Adresse e-mail', _email,
          indice: 'vous@exemple.ch', clavier: TextInputType.emailAddress),
      const SizedBox(height: 12),
      _champDePhrase(),
    ];
  }

  List<Widget> _bascules(Gc gc) => [
        // La phrase de récupération n'est proposée qu'au déverrouillage : à la connexion,
        // c'est le mot de passe du compte qu'on tape, et ils ne s'échangent pas.
        if (_coffreFerme || _reprise)
          _bascule(
            gc,
            'Utiliser ma phrase de récupération',
            _parRecuperation,
            (v) => setState(() => _parRecuperation = v),
          ),
        if (_reprise)
          TextButton(
            onPressed: () => setState(() {
              _changerDeCompte = true;
              _parRecuperation = false;
            }),
            child: const Text('Changer de compte ou de serveur'),
          ),
      ];

  Widget _bascule(Gc gc, String titre, bool valeur, ValueChanged<bool> auChangement) =>
      Row(
        children: [
          Expanded(child: Text(titre, style: TextStyle(color: gc.estompe, fontSize: 13))),
          Switch(value: valeur, onChanged: auChangement),
        ],
      );

  Widget _encart(Gc gc, String texte) => Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: gc.surface2,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: gc.bordure),
        ),
        child: Text(texte, style: TextStyle(color: gc.encre, fontSize: 13)),
      );

  Widget _champ(
    String titre,
    TextEditingController controleur, {
    String? indice,
    TextInputType? clavier,
  }) =>
      Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(titre, style: TextStyle(color: Gc.of(context).estompe, fontSize: 12)),
          const SizedBox(height: 6),
          TextField(
            controller: controleur,
            keyboardType: clavier,
            autocorrect: false,
            enableSuggestions: false,
            textCapitalization: TextCapitalization.none,
            decoration: InputDecoration(hintText: indice),
          ),
        ],
      );

  Widget _champDePhrase() => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            _parRecuperation ? 'Phrase de récupération' : 'Mot de passe',
            style: TextStyle(color: Gc.of(context).estompe, fontSize: 12),
          ),
          const SizedBox(height: 6),
          TextField(
            controller: _phrase,
            obscureText: !_phraseVisible,
            autocorrect: false,
            enableSuggestions: false,
            onSubmitted: (_) => _valider(),
            decoration: InputDecoration(
              suffixIcon: IconButton(
                icon: Icon(_phraseVisible ? Icons.visibility_off : Icons.visibility),
                // Une phrase de récupération fait douze mots : la taper à l'aveugle
                // garantit la faute de frappe, et l'erreur rendue ne dit pas où.
                tooltip: _phraseVisible ? 'Masquer' : 'Afficher',
                onPressed: () => setState(() => _phraseVisible = !_phraseVisible),
              ),
            ),
          ),
        ],
      );
}
