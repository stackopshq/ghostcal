import 'package:flutter/material.dart';

import '../l10n/generated/app_localisations.dart';
import '../outils/fuseaux.dart';
import '../theme.dart';

/// Searchable list of time zones. What is typed can be used as is when it is not in
/// the list: the server knows every IANA zone, the list only the common ones.
class ChoixDuFuseau extends StatefulWidget {
  const ChoixDuFuseau({super.key});

  @override
  State<ChoixDuFuseau> createState() => _ChoixDuFuseauState();
}

class _ChoixDuFuseauState extends State<ChoixDuFuseau> {
  String _requete = '';

  @override
  Widget build(BuildContext context) {
    final gc = Gc.of(context);
    final resultats = filtrerLesFuseaux(_requete);
    final saisie = _requete.trim();
    return SafeArea(
      child: SizedBox(
        height: MediaQuery.of(context).size.height * 0.75,
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
              child: TextField(
                autofocus: true,
                decoration: InputDecoration(
                  prefixIcon: const Icon(Icons.search),
                  hintText: L.of(context).rechercherUnFuseau,
                ),
                onChanged: (v) => setState(() => _requete = v),
              ),
            ),
            Expanded(
              child: ListView(
                children: [
                  for (final f in resultats)
                    ListTile(
                      title: Text(f.replaceAll('_', ' ')),
                      onTap: () => Navigator.of(context).pop(f),
                    ),
                  if (saisie.contains('/') && !resultats.contains(saisie))
                    ListTile(
                      leading: Icon(Icons.edit_outlined, color: gc.estompe),
                      title: Text(saisie),
                      onTap: () => Navigator.of(context).pop(saisie),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
