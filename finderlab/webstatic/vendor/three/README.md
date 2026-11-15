# Vendored Three.js r170 (0.170.0)

Upstream: https://github.com/mrdoob/three.js/tree/r170
License: MIT, retained verbatim in LICENSE (copyright 2010–2024 three.js authors).
Downloaded from the upstream r170 tag, not a runtime CDN dependency.

Files / upstream SHA-256:

- build/three.module.min.js: 08fd7545d13d2c7fb65ab691530a802dafefd638596501854f267d0fb13c39e7
- examples/jsm/controls/OrbitControls.js: 80efaadea4f8a636a65fb0bd08bfef62f3d93a0bb94e2e7500f23176c5c07f4e
- LICENSE: 4c40a1ef62450b857c3b2aaf294936304cd552d965fbcd9d32d4c5bcf4ba4454

Local modification: OrbitControls' single bare import `from 'three'` changed to
`from './three.module.min.js'` for local browser modules without import maps or
a bundler. No other upstream code changes. Original blobs can be recovered
from the pinned tag/URLs and hashes above. No other Three.js addons are shipped.

This browser-only dependency adds no Python/npm install requirement. Update
intentionally with license/integrity review and preview regression checks.
