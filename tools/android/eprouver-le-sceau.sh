#!/usr/bin/env bash
# Éprouve, sur émulateur, que la phrase scellée meurt avec l'enrôlement qui l'a scellée.
#
# ─── Ce qu'il orchestre ───
#
#   1. lance `integration_test/biometrie_scelle_test.dart`, qui scelle et relit ;
#   2. pose un doigt enrôlé tant que le test en a besoin ;
#   3. **suspend** les poses, le temps d'enrôler une empreinte de plus — les poses de
#      l'ancien doigt perturbent l'enrôlement du nouveau, constaté : le compte restait à 3 ;
#   4. reprend les poses pour la seconde lecture.
#
# ─── Pourquoi reprendre les poses à l'étape 4 ───
#
# C'est le point le plus délicat du dispositif. Si la garantie **ne tenait pas**, la
# seconde lecture ouvrirait une invite biométrique ; sans personne pour y répondre elle
# échouerait sur un délai, et le test conclurait « illisible, donc la garantie tient ».
# Le piège penche du côté de ce qu'on espère, ce qui le rend facile à ne pas voir. En
# posant un doigt toujours enrôlé, une garantie absente se traduit par une lecture
# **réussie**, et le témoin tombe comme il doit.
set -euo pipefail

RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ADB="${ADB:-$HOME/Library/Android/sdk/platform-tools/adb}"
APPAREIL="${APPAREIL:-emulator-5554}"
# Un doigt déjà enrôlé, qui le restera après le nouvel enrôlement.
DOIGT_CONNU="${DOIGT_CONNU:-1}"
JOURNAL="${JOURNAL:-${TMPDIR:-/tmp}/ghostcal-sceau.log}"

export ANDROID_HOME="${ANDROID_HOME:-$HOME/Library/Android/sdk}"
export JAVA_HOME="${JAVA_HOME:-/opt/homebrew/opt/openjdk@21}"
export PATH="$JAVA_HOME/bin:$PATH"

say() { printf "\n\033[1m▸ %s\033[0m\n" "$*" >&2; }

# Les poses, dans un processus qu'on peut suspendre et reprendre.
POSEUR=""
poser() {
  [[ -n "$POSEUR" ]] && return 0
  ( while true; do
      "$ADB" emu finger touch "$DOIGT_CONNU" >/dev/null 2>&1
      sleep 1
      "$ADB" emu finger remove >/dev/null 2>&1
      sleep 1
    done ) &
  POSEUR=$!
}
cesser() { [[ -n "$POSEUR" ]] && kill "$POSEUR" 2>/dev/null; POSEUR=""; }
trap 'cesser; [[ -n "${TEST:-}" ]] && kill "$TEST" 2>/dev/null' EXIT

# Le marqueur **d'exécution**, pas la ligne de source.
#
# Le premier jet cherchait simplement le texte dans le journal : il le trouvait dans
# l'écho du source que le cadre de test imprime quand la compilation échoue, et concluait
# que le test avait avancé alors qu'il n'avait jamais démarré. On exige donc une ligne qui
# **commence** par le marqueur.
attendre_marqueur() {
  local marqueur="$1" limite="$2" i=0
  while (( i < limite )); do
    grep -qE "^TEMOIN: $marqueur" "$JOURNAL" 2>/dev/null && return 0
    grep -q "Some tests failed\|Failed to load" "$JOURNAL" 2>/dev/null && return 1
    sleep 2; i=$((i+1))
  done
  return 1
}

: >"$JOURNAL"
say "Lancement du témoin (journal : $JOURNAL)"
cd "$RACINE/apps/mobile"
flutter test integration_test/biometrie_scelle_test.dart -d "$APPAREIL" >"$JOURNAL" 2>&1 &
TEST=$!

say "Poses du doigt $DOIGT_CONNU pour la première lecture"
poser

if ! attendre_marqueur "scellé et relu" 180; then
  cesser
  echo "Le témoin n'a pas atteint l'état « scellé et relu »." >&2
  tail -30 "$JOURNAL" >&2
  exit 1
fi

say "Scellé et relu — suspension des poses pour l'enrôlement"
cesser
sleep 2

"$RACINE/tools/android/enroler.sh"

say "Reprise des poses pour la seconde lecture"
poser

wait "$TEST"; CODE=$?
cesser

say "Résultat"
grep -E "^TEMOIN:|All tests passed|Some tests failed|GARANTIE NE TIENT" "$JOURNAL" || true
exit "$CODE"
