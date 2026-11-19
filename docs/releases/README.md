# Notes de version

Un fichier par version, nommé comme son étiquette : `mobile-v1.9.0.md`. Il devient le texte
de la page Release de `github.com/stackopshq/ghostcal`, en français comme les précédentes.

## Publier une version

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

Le job échoue s'il manque les notes ou si l'étiquette ne correspond pas à `pubspec.yaml`. Il
ne fait rien si `GITHUB_RELEASE_TOKEN` est absent, et il ne remplace pas une Release qui
existe déjà.
