# affection_memory release metadata

`official-release-fragment.json` is the reviewable input for the official catalog
builder. The deterministic package is produced by `package_builder.py`; neither
the package nor this directory contains relationship state, saved memories,
profiles, environment values, caches, models, vendor trees, or install scripts.

Uninstall preserves both historical personal-data files. Purge is restricted to
the declared `affection_memory` module-data namespace and must never target those
historical paths.
