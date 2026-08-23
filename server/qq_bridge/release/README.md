# QQ Bridge release candidate

- Module: `qq_bridge`
- Version: `0.1.26`
- Tag: `modules-2026.08.20`
- Asset: `qq_bridge-0.1.26.zip`
- Deterministic asset size: `172429` bytes
- Deterministic asset SHA-256: `9ab9c65ab25e7c357338f4654f3d46f383bb5f34d8179aa19c703ae89c5f8ae0`
- Manifest SHA-256: `2d5e4ff59cd2684efb4c1a82c157a74c731e89b1ccddfe7f01c999814e13de2f`
- Runtime requirement: Node.js `20/22/24/26` x64; Node 24 LTS recommended
- Adapter: Core-registered `qq_bridge`
- Data policy: preserve persistent `.env` and sidecar runtime data on update or uninstall
- Dependency policy: `node_modules` is never bundled; PK-020 atomically prepares the fixed sidecar allowlist and lockfile under the separate versioned dependency deployment root
- Runtime entry: only `<dependency-root>/src/index.mjs`, after strict deployment marker and content verification

This directory is release metadata only. It is not a published Release and does
not contain credentials, personal state, caches, logs, runtime dependencies or
the generated ZIP.
