import 'dart:math';

import 'package:flutter/material.dart';

import '../l10n/generated/app_localisations.dart';
import '../theme.dart';

/// The custom questions of an event type, edited in place in its `questions` list.
///
/// Same shape as the web (`BookingQuestionSchema`): `{id, label, type, required, options}`.
/// Ids are generated like the web's, and kept on edit: answers already sealed by invitees
/// are keyed by them.
class QuestionsDuType extends StatelessWidget {
  const QuestionsDuType({
    super.key,
    required this.questions,
    required this.changer,
  });

  final List<Map<String, dynamic>> questions;
  final ValueChanged<List<Map<String, dynamic>>> changer;

  static const types = ['text', 'textarea', 'phone', 'select', 'checkbox'];

  static String libelleDuType(L l, String type) => switch (type) {
    'textarea' => l.reponseLongue,
    'phone' => l.reponseTelephone,
    'select' => l.reponseChoix,
    'checkbox' => l.reponseCase,
    _ => l.reponseTexte,
  };

  static String nouvelId(int rang) {
    const alphabet = 'abcdefghijklmnopqrstuvwxyz0123456789';
    final r = Random.secure();
    return 'q${rang}_${List.generate(5, (_) => alphabet[r.nextInt(alphabet.length)]).join()}';
  }

  Future<void> _editer(BuildContext context, int? rang) async {
    final depart = rang == null
        ? {
            'id': nouvelId(questions.length + 1),
            'label': '',
            'type': 'text',
            'required': false,
            'options': <String>[],
          }
        : Map<String, dynamic>.of(questions[rang]);
    final resultat = await showModalBottomSheet<Map<String, dynamic>>(
      context: context,
      isScrollControlled: true,
      builder: (_) =>
          _EditeurDeQuestion(depart: depart, nouvelle: rang == null),
    );
    if (resultat == null) return;
    final liste = [...questions];
    if (rang == null) {
      liste.add(resultat);
    } else {
      liste[rang] = resultat;
    }
    changer(liste);
  }

  @override
  Widget build(BuildContext context) {
    final l = L.of(context);
    final gc = Gc.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox(height: 20),
        Text(
          l.questionsAuxInvites,
          style: TextStyle(fontSize: 12, color: gc.estompe),
        ),
        const SizedBox(height: 4),
        Text(
          l.questionsExplication,
          style: TextStyle(fontSize: 12, color: gc.estompe),
        ),
        for (var i = 0; i < questions.length; i++)
          ListTile(
            key: Key('question.$i'),
            contentPadding: EdgeInsets.zero,
            title: Text(
              '${questions[i]['label']}${questions[i]['required'] == true ? ' *' : ''}',
            ),
            subtitle: Text(libelleDuType(l, '${questions[i]['type']}')),
            onTap: () => _editer(context, i),
            trailing: IconButton(
              icon: const Icon(Icons.delete_outline),
              tooltip: l.supprimer,
              onPressed: () => changer([...questions]..removeAt(i)),
            ),
          ),
        TextButton.icon(
          key: const Key('question.ajouter'),
          onPressed: questions.length >= 30
              ? null
              : () => _editer(context, null),
          icon: const Icon(Icons.add),
          label: Text(l.ajouterUneQuestion),
        ),
      ],
    );
  }
}

class _EditeurDeQuestion extends StatefulWidget {
  const _EditeurDeQuestion({required this.depart, required this.nouvelle});

  final Map<String, dynamic> depart;
  final bool nouvelle;

  @override
  State<_EditeurDeQuestion> createState() => _EditeurDeQuestionState();
}

class _EditeurDeQuestionState extends State<_EditeurDeQuestion> {
  late final _libelle = TextEditingController(
    text: '${widget.depart['label'] ?? ''}',
  );
  late final _options = TextEditingController(
    text: ((widget.depart['options'] as List?) ?? const []).join('\n'),
  );
  late String _type = '${widget.depart['type'] ?? 'text'}';
  late bool _obligatoire = widget.depart['required'] == true;

  @override
  void dispose() {
    _libelle.dispose();
    _options.dispose();
    super.dispose();
  }

  List<String> get _choix => _options.text
      .split('\n')
      .map((o) => o.trim())
      .where((o) => o.isNotEmpty)
      .take(50)
      .toList();

  bool get _valide =>
      _libelle.text.trim().isNotEmpty &&
      (_type != 'select' || _choix.isNotEmpty);

  @override
  Widget build(BuildContext context) {
    final l = L.of(context);
    return Padding(
      padding: EdgeInsets.fromLTRB(
        20,
        16,
        20,
        20 + MediaQuery.viewInsetsOf(context).bottom,
      ),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              widget.nouvelle ? l.ajouterUneQuestion : l.modifierLaQuestion,
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 12),
            TextField(
              key: const Key('question.libelle'),
              controller: _libelle,
              maxLength: 200,
              autofocus: widget.nouvelle,
              onChanged: (_) => setState(() {}),
              decoration: InputDecoration(labelText: l.libelleDeLaQuestion),
            ),
            DropdownButtonFormField<String>(
              key: const Key('question.type'),
              initialValue: _type,
              decoration: InputDecoration(labelText: l.typeDeReponse),
              items: [
                for (final t in QuestionsDuType.types)
                  DropdownMenuItem(
                    value: t,
                    child: Text(QuestionsDuType.libelleDuType(l, t)),
                  ),
              ],
              onChanged: (t) => setState(() => _type = t ?? 'text'),
            ),
            if (_type == 'select') ...[
              const SizedBox(height: 12),
              TextField(
                key: const Key('question.options'),
                controller: _options,
                minLines: 3,
                maxLines: 6,
                onChanged: (_) => setState(() {}),
                decoration: InputDecoration(labelText: l.choixUnParLigne),
              ),
            ],
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(l.reponseObligatoire),
              value: _obligatoire,
              onChanged: (v) => setState(() => _obligatoire = v),
            ),
            const SizedBox(height: 8),
            BoutonPrincipal(
              key: const Key('question.valider'),
              onPressed: _valide
                  ? () => Navigator.pop(context, {
                      ...widget.depart,
                      'label': _libelle.text.trim(),
                      'type': _type,
                      'required': _obligatoire,
                      'options': _type == 'select' ? _choix : <String>[],
                    })
                  : null,
              child: Text(l.valider),
            ),
          ],
        ),
      ),
    );
  }
}
