#!/usr/bin/env bash
# Enrôle une empreinte de plus sur l'émulateur, par l'interface des Réglages.
#
# ─── Pourquoi par l'interface ───
#
# Le HAL « ranchu » de l'émulateur n'expose aucune commande d'enrôlement : `cmd fingerprint`
# ne sait que `sync`, `fingerdown` et `notification`, et les propriétés du HAL virtuel
# (`persist.vendor.fingerprint.virtual.*`) n'existent pas sur cette image. Il reste les
# Réglages, qu'on pilote au doigt.
#
# ─── À quoi il sert ───
#
# À provoquer, depuis l'hôte, le seul événement qui éprouve vraiment le magasin scellé :
# l'arrivée d'une nouvelle empreinte. `integration_test/biometrie_scelle_test.dart` scelle
# une phrase, la relit, puis attend que ce script ait fait son travail.
#
# ─── Ce qu'il vérifie de lui-même ───
#
# Il compte les empreintes avant et après, et **échoue si le compte n'a pas augmenté**.
# Sans cela il rendrait 0 en n'ayant rien fait — et le test qu'il sert conclurait « la
# garantie tient » alors que rien n'aurait changé. C'est le mode de défaillance le plus
# coûteux du dispositif, parce qu'il va dans le sens de ce qu'on espère.
set -euo pipefail

ADB="${ADB:-$HOME/Library/Android/sdk/platform-tools/adb}"
CODE="${CODE_EMULATEUR:-1234}"
# Un identifiant de doigt qui n'est pas déjà enrôlé.
DOIGT="${DOIGT:-7}"

say() { printf "\n\033[1m▸ %s\033[0m\n" "$*" >&2; }

compter() {
  # `grep -o` sur le vidage du service : le nombre d'empreintes du profil 0.
  "$ADB" shell "dumpsys fingerprint" 2>/dev/null |
    grep -o '"count":[0-9]*' | head -1 | cut -d: -f2
}

AVANT="$(compter)"
say "Empreintes avant : ${AVANT:-inconnu}"
[[ -z "$AVANT" ]] && { echo "Impossible de lire le compte d'empreintes." >&2; exit 1; }

say "Ouverture de l'enrôlement"
"$ADB" shell am start -a android.settings.FINGERPRINT_ENROLL >/dev/null 2>&1
sleep 4

# Le code de verrouillage, si on le demande.
if "$ADB" shell dumpsys activity activities 2>/dev/null | grep -q "ConfirmLockPassword"; then
  say "Saisie du code"
  "$ADB" shell input text "$CODE" >/dev/null 2>&1
  "$ADB" shell input keyevent 66 >/dev/null 2>&1
  sleep 4
fi

# Les deux écrans d'introduction : « MORE » puis « I AGREE », au même endroit.
say "Passage des écrans d'introduction"
for _ in 1 2 3; do
  "$ADB" shell input tap 255 580 >/dev/null 2>&1
  sleep 2
done

say "Pose du doigt $DOIGT, jusqu'à ce que l'enrôlement soit complet"
for _ in $(seq 1 25); do
  "$ADB" shell dumpsys activity activities 2>/dev/null |
    grep -q "FingerprintEnrollFinish" && break
  "$ADB" emu finger touch "$DOIGT" >/dev/null 2>&1
  sleep 1
  "$ADB" emu finger remove >/dev/null 2>&1
  sleep 1
done

APRES="$(compter)"
say "Empreintes après : ${APRES:-inconnu}"

if [[ "${APRES:-0}" -le "${AVANT:-0}" ]]; then
  echo >&2
  echo "L'enrôlement n'a rien ajouté ($AVANT → $APRES)." >&2
  echo "Le test qui s'appuie dessus conclurait au vert sans que rien ait changé." >&2
  exit 1
fi

say "Enrôlement fait : $AVANT → $APRES"
