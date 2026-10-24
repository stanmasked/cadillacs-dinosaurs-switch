# Stage362 — restore synthetic CI without weakening private ROM guard

Stage361 Python CI run 40029687406 failed in four tests because the
production prohibition on processing private data in GitHub Actions was
applied to **synthetic fixture calls**. The production tool correctly refuses
`GITHUB_ACTIONS=true`; that guarantee remains unchanged.

Four synthetic-only test call sites now temporarily replace the guard using
`unittest.mock.patch.object` solely within fixture testing. Dedicated
public-runner rejection tests call the unpatched production guard and assert
that it rejects invocation before attempting private disk access.
The production implementation, source pins and archival policy were not changed.

Validation: from the Stage361 local test workspace, the 12 isolated tests
completed successfully with `GITHUB_ACTIONS=true`. Recheck the complete
GitHub Actions Python and Nintendo Switch workflows on the Stage362 commit.
A passing Python CI is not evidence of a real MAME -verifyroms invocation.

Private Stage361 ROM inventory audit still stands at 16 of 16 checksum-valid
ROM payloads. Actual native historical MAME -verifyroms and dino.inp playback
remain unverified; no ROM/INP/WLF/extracted assets are uploaded to GitHub.
