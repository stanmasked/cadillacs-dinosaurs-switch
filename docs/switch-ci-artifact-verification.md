# Verifying the CI-built Nintendo Switch bootstrap (stage 54)

This repository's `Nintendo Switch native bootstrap` workflow builds a
**ROM-free CPS-1 technical inspector**. It is not a playable remaster,
it does not ship arcade game ROMs, and it does not prove that its rendering
matches original MAME output.

## When the build runs

The workflow builds on source/Makefile changes, on code or test pull
requests (`source/**`, `tools/**`, `tests/**`), and when explicitly
selected with **Run workflow** in the GitHub Actions UI. A build from an
earlier feature branch is not evidence that the current PR builds.

The workflow runs in `devkitpro/devkita64:20260219` and does the following:

1. `make -j2` builds `cadillacs-dinosaurs-switch.nro`.
2. Checks the NRO is nonempty and has `NRO0` at byte offset `0x10`,
   the standard Nintendo Switch NRO header signature.
3. Writes `cadillacs-dinosaurs-switch.nro.sha256` using
   `sha256sum` and immediately verifies the checksum with
   `sha256sum --check`.
4. Uploads **both files together** in the GitHub Actions artifact
   `cadillacs-dinosaurs-switch-bootstrap`.

## Download and verify

Open the successful workflow run in **Actions** and download its
`cadillacs-dinosaurs-switch-bootstrap` artifact. After extracting
the archive, work in the directory that contains both files.

On Linux:

```sh
sha256sum --check cadillacs-dinosaurs-switch.nro.sha256
```

On macOS (built-in tool):

```sh
shasum -a 256 cadillacs-dinosaurs-switch.nro
cat cadillacs-dinosaurs-switch.nro.sha256
```

Compare the two displayed hex digests. The SHA-256 checksum detects
accidental changes between the CI artifact and the extracted NRO.
It does **not** independently authenticate the build, the repository
publisher, the correctness of the original game, or the physical
Nintendo Switch hardware. For stronger provenance, verify the run's
commit SHA and workflow definition on GitHub.

**Safety:** This is only a homebrew NRO for compatible development
hardware; never treat it as a Nintendo eShop title or a commercial
Cadillacs and Dinosaurs release. No genuine arcade game data is
included in the artifact.
