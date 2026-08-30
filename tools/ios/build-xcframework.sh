#!/usr/bin/env bash
# Construit le cœur crypto en XCFramework consommable par Xcode, bindings Swift compris.
#
# Sortie : apps/ios/GhostcalCrypto.xcframework + apps/ios/Generated/*.swift
# Prérequis : macOS avec Xcode (pour `xcodebuild -create-xcframework` et `lipo`).
#
# Les bindings Swift sont générés à partir de la bibliothèque *déjà compilée*
# (`--library`) et non d'un fichier UDL : c'est ce qui garantit que la surface Swift
# décrit le binaire réellement embarqué, et pas une déclaration qui aurait divergé.
set -euo pipefail

# Le cœur cryptographique vit dans le dépôt de la suite, pas ici — une seule
# implémentation pour tous les produits, décision consignée dans son ADR 0001. Ce dépôt
# n'en garde donc aucune copie.
#
# `GHOSTSUITE` dit où le trouver ; par défaut, un clone voisin. Ce n'est pas la forme
# définitive : distribuer l'XCFramework construit plutôt que le compiler chez chaque
# produit éviterait d'exiger un second dépôt sur chaque poste. À trancher.
CRATE=ghost-crypto-ffi
LIB=libghost_crypto_ffi.a
PRODUIT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ROOT="${GHOSTSUITE:-$(cd "$PRODUIT/.." && pwd)/suite}"
if [[ ! -d "$ROOT/crates/$CRATE" ]]; then
  echo "Cœur commun introuvable : $ROOT/crates/$CRATE" >&2
  echo "Clonez git@git.stackops.ch:stackops/ghostsuite.git à côté de ce dépôt," >&2
  echo "ou indiquez son chemin :  GHOSTSUITE=/chemin/vers/ghostsuite $0" >&2
  exit 1
fi
OUT="$PRODUIT/apps/ios"
BUILD="$ROOT/target"

cd "$ROOT"

for target in aarch64-apple-ios aarch64-apple-ios-sim x86_64-apple-ios; do
  rustup target add "$target" >/dev/null
  # `--lib` seulement : le binaire `uniffi-bindgen` est un outil d'hôte, il n'a
  # rien à faire dans une compilation croisée vers iOS.
  cargo build --release --lib -p "$CRATE" --target "$target"
done

# Le simulateur doit accepter les deux architectures (Apple Silicon et Intel),
# et un XCFramework n'admet qu'une tranche par plateforme : d'où le `lipo`.
SIM="$BUILD/ios-simulator"
mkdir -p "$SIM"
lipo -create \
  "$BUILD/aarch64-apple-ios-sim/release/$LIB" \
  "$BUILD/x86_64-apple-ios/release/$LIB" \
  -output "$SIM/$LIB"

rm -rf "$OUT/Generated" "$OUT/Headers" "$OUT/GhostcalCrypto.xcframework"
mkdir -p "$OUT/Generated" "$OUT/Headers"

cargo run --release --bin uniffi-bindgen -- generate \
  --library "$BUILD/aarch64-apple-ios/release/$LIB" \
  --language swift \
  --out-dir "$OUT/Generated"

# Xcode exige que la carte de modules s'appelle `module.modulemap` et voisine les en-têtes.
mv "$OUT/Generated"/*.h "$OUT/Headers/"
mv "$OUT/Generated"/*.modulemap "$OUT/Headers/module.modulemap"

xcodebuild -create-xcframework \
  -library "$BUILD/aarch64-apple-ios/release/$LIB" -headers "$OUT/Headers" \
  -library "$SIM/$LIB" -headers "$OUT/Headers" \
  -output "$OUT/GhostcalCrypto.xcframework"

echo "XCFramework : $OUT/GhostcalCrypto.xcframework"
echo "Bindings Swift : $OUT/Generated"
