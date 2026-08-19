# QQ Bridge release candidate

- Module: `qq_bridge`
- Version: `0.1.24`
- Tag: `modules-2026.08.12`
- Asset: `qq_bridge-0.1.24.zip`
- Deterministic asset size: `161683` bytes
- Deterministic asset SHA-256: `2a760c6303fa353bcaf8882333b263ad5ca30839b3a07de9aa195cfa48eaaf67`
- Manifest SHA-256: `1535258b9c1307eb50241d1969704aa0d7ba170a0c5957f9f94e67cb73aa30e1`
- Runtime requirement: Node.js `20/22/24/26` x64; Node 24 LTS recommended
- Adapter: Core-registered `qq_bridge`
- Data policy: preserve persistent `.env` and sidecar runtime data on update or uninstall
- Dependency policy: `node_modules` is never bundled; PK-020 atomically prepares the fixed sidecar allowlist and lockfile under the separate versioned dependency deployment root
- Runtime entry: only `<dependency-root>/src/index.mjs`, after strict deployment marker and content verification

This directory is release metadata only. It is not a published Release and does
not contain credentials, personal state, caches, logs, runtime dependencies or
the generated ZIP.
