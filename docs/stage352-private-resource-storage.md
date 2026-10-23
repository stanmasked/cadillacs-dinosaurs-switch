# Cadillacs and Dinosaurs Remake — private resource and data storage policy

Stage352 records the storage rules for original and extracted game materials. This file contains policy only; it must not contain ROM bytes, extracted assets, recording contents, private paths, or secrets.

## Authoritative originals

- `Cadillac Dinosaur.zip`, `dino.inp`, and `dino.wlf` remain private and unmodified.
- The private Google Drive originals are the durable source copies. Do not overwrite, rename, or replace them as part of extraction.
- Never commit originals, extracted game assets, gameplay captures, or detailed private replay logs to the public repository.

## Extracted resources and derived data

- Keep durable copies in the project's private storage, not in Git or public CI artifacts.
- For large data archives, split the archive into independently verifiable parts smaller than 256 MiB each before private upload.
- Reconstruct parts only in an isolated, non-synchronized local working directory. Verify each part and the reconstructed output with SHA-256 before using it.
- Record hashes and provenance in a private manifest. A newly calculated hash establishes consistency with the recorded copy; it does not by itself prove provenance unless compared with a trusted source hash.
- Do not write extracted files into Google Drive's synchronized local folder as a scratch workspace. The Drive copy is for durable private storage; extraction and analysis happen in a separate local workspace.

## Temporary files and interrupted work

- Use a dedicated, isolated temporary directory for each operation and keep it outside the repository.
- If an incomplete `.pending` copy or reconstruction exists, stop and inspect/verify it before resuming. Do not automatically overwrite, open as trusted input, or delete it.
- Remove generated temporary files only after the relevant verification/report has been captured and no process is using them. Cleanup of CI runtime files must not target the private source/archive location.
- If verification fails, preserve the failed state for diagnosis without promoting it to the trusted resource set.

## GitHub Actions boundary

- Public CI may contain source code, synthetic fixtures, checksums of public technical dependencies, and minimal redacted technical diagnostics only.
- Never upload original or extracted game data, INP/WLF recordings, MNG gameplay frames, or full replay traces to public Actions artifacts.
- Technical runtime artifacts are short-lived and retained for no more than three days. The workflow must clean its ephemeral runner workspace even after failure.
- A passing source/build/privacy check does not prove that the original game or private recording replayed successfully.
