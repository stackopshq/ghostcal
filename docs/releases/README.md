# Notes de version

Un fichier par version, nommé comme son étiquette. Il devient le texte de la page Release de
`github.com/stackopshq/ghostcal`. Deux sortes d'étiquettes :

- `vX.Y.Z`, le **serveur** : notes en anglais, pour ceux qui hébergent GhostCal (ce qui
  change, ce qu'il faut régler dans `.env`, ce qu'il faut faire avant de mettre à jour) ;
- `mobile-vX.Y.Z`, les **applications** : notes en français, comme les précédentes.

## Publier une version du serveur

1. Dans une MR : la version dans `pyproject.toml` (`version = "0.2.0"`) et
   `docs/releases/v0.2.0.md`. La faire relire, la fusionner.
2. Attendre que le pipeline de `main` soit vert.
3. Poser l'étiquette `v0.2.0` sur ce commit de `main` (mainteneurs : l'étiquette est protégée).

Le pipeline de l'étiquette refait tous les contrôles, publie `ghcr.io/stackopshq/ghostcal:v0.2.0`
(job `images`), puis crée la Release `GhostCal v0.2.0` (job `release-github`). Il échoue si
l'étiquette ne correspond pas à `pyproject.toml`.

## Publier une version des applications

1. Dans une MR : la version dans `apps/mobile/pubspec.yaml` (`1.9.0+16`) et
   `docs/releases/mobile-v1.9.0.md`. La faire relire, la fusionner.
2. Poser l'étiquette `mobile-v1.9.0` sur ce commit de `main`. Seuls les mainteneurs le
   peuvent : l'étiquette est protégée, et c'est ce qui lui donne le jeton GitHub.
3. Le job `release-github` crée la Release, intitulée `GhostCal 1.9.0 (16)`, une fois que le
   miroir a poussé l'étiquette sur GitHub.
4. Depuis le Mac, y joindre les fichiers construits et signés :
   `gh release upload mobile-v1.9.0 --repo stackopshq/ghostcal GhostCal-1.9.0.dmg <aab> <apk> SHA256SUMS`.
   Pas `gh release create` : la Release existe déjà, il échouerait.
5. Vérifier que l'image se télécharge sans jeton (`docs/macos.md`), puis seulement signer
   l'entrée d'appcast. Sparkle ne propose rien tant qu'elle n'est pas posée.

Le job échoue s'il manque les notes ou si l'étiquette ne correspond pas au fichier de version. Il
ne fait rien si `GITHUB_RELEASE_TOKEN` est absent, et il ne remplace pas une Release qui
existe déjà.
