# ghost-crypto (WebAssembly)

**Generated, do not edit.** Built from the suite's crypto core, `ghostsuite`
commit `bb0a6bc`, crate `crates/ghost-crypto-wasm`:

    wasm-pack build --release --target web

then the four `pkg/ghost_crypto_wasm*` files copied here. To update, rebuild
there and copy again; never patch these files (ADR-0001: no product
reimplements a primitive). `src/lib/e2e.ts` is the only importer.
