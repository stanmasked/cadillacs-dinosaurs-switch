# Stage402 — prefer Wine Unix-library directories in CI

## Reason

Stage401 proved that Wine 10.0 in the extracted Debian runtime could load its version path when `WINEDLLPATH` included `/usr/lib/i386-linux-gnu/wine/i386-unix`. However, the first workflow edit exported only the parent directories. Because the variable was already set, the launcher correctly preserved it instead of applying its fallback discovery, leaving CI different from the successful local probe.

## Change

- Added the i386 `i386-unix` and amd64 `x86_64-unix` library directories before the parent directories in both the Wine32 bootstrap and native Wine64 fallback blocks.
- Updated the regression tests to assert the exact path list and that the Unix-specific paths are present before parent fallbacks.
- Kept the caller-supplied `WINEDLLPATH` override behavior unchanged.

## Validation status

The patch is committed to the existing Draft PR branch. Local container access to GitHub is unavailable in this session, so a fresh repository clone and execution of the full Python test suite could not be performed here. The added regression test will run in GitHub Actions once the queued jobs are scheduled. A successful Wine version probe is not evidence that MAME starts or that the original game replays correctly.

No ROM, INP/WLF, extracted game resources, or gameplay captures were added to GitHub.
