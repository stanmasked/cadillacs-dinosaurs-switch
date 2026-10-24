# Stage364 — Independent owner-private CPS-1 GFX backup recovery

This stage tests the ability to restore the existing Stage363 owner-private
CPS-1 graphics backup after losing a temporary execution container. It
**does not** run MAME, confirm source recording playback, or capture original
video. The atlas images are grayscale diagnostics of authentic ROM pixel
indices, **not** original palette colours or gameplay frames.

`tools/cps1_private_graphics_restore.py` independently checks an archived
4-MiB graphics region, eight reversible source lanes, and two 256×256 PNG
atlases. It checks the complete original backup ZIP SHA-256 and private
manifest SHA-256 against independent expected digests. Both values must be
provided separately from the archive being audited; comparing only an
embedded manifest to itself is insufficient. Each of the four ZIP entries
is checked, including exact equality of the embedded and external private
manifests. The tool validates source-lane reverse interleaving, image
format/CRC/inflate bounds, entry sizes, and no unexpected files or symlinks.

For safe *audit only* (no extraction):

```sh
python -m tools.cps1_private_graphics_restore \
  --archive /private/Stage363_CPS1_GFX_Region_and_Atlases.zip \
  --manifest /private/Stage363_CPS1_GFX_Manifest.json \
  --archive-sha256 '<independently-recorded-private-ZIP-SHA256>' \
  --manifest-sha256 '<independently-recorded-private-manifest-SHA256>'
```

Add `--restore-to /private/new-empty-output-dir` to restore atomically,
never overwriting existing output. Store inputs and outputs outside the
public repository and public Actions runner. Actual tests that process
original assets refuse `GITHUB_ACTIONS=true`; public tests generate only
synthetic tile streams and PNG fixtures and narrowly stub this gate inside
synthetic test helpers. Dedicated tests preserve the real GitHub Actions
refusal. The restored archive is **only** a locally derived copy; the
owner-only Google Drive original backup remains canonical.

Private offline recovery was performed successfully against a freshly
redownloaded owner-only Google Drive ZIP and manifest. All 4 ZIP entries,
8 reverse-interleaved graphics lanes, 2 PNG scanline structures and restored
file SHA-256 digests passed. 14 synthetic tests passed in a simulated
GitHub Actions environment without processing game data. Public GitHub
contains code, synthetic tests, and this ROM-free document only; private
archive, manifest, extracted image pixels, source ROM, recording and raw
execution traces remain exclusively in owner-managed private Google Drive.

**Status limit:** archived bytes restored and checked, but historical
MAME 0.106 `-verifyroms dino` and `dino.inp` input playback remain **NOT RUN**.