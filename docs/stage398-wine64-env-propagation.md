# Stage398 — preserve the Wine64 execution environment after bootstrap

## Why this follow-up is needed

Stage397 corrected prefix initialization to call the native Wine64 loader directly. The follow-on MAME probes still needed the same \`WINELOADER\` and multiarch \`WINEDLLPATH\` environment, however: the variables passed to a single \`env\` command do not persist into later shell commands. Without exporting them, the \`-help\` probe could fall back to a different loader configuration and report a misleadingly different error.

## Change

The Wine64 fallback now exports \`WINELOADER\` and the i386/amd64 Wine DLL roots alongside \`WINE_BIN\` before it runs version, bootstrap, help, showconfig or listxml checks. The workflow regression test verifies that the environment is exported and that the native PE bootstrap is invoked directly.

This is diagnostic consistency, not a claim that Wine64 can run the historical 32-bit MAME binary. The local attempt with the same variables still did not produce the expected MAME 0.106 help marker, so CI must determine the exact next failure stage.

## Guardrails

- Only the public ROM-free MAME 0.106 technical artifact and public Debian Wine packages are involved.
- No original ROM, INP/WLF recordings, extracted game resources, or gameplay captures enter public CI.
- The result is not accepted as native MAME execution or game-playback evidence.
- Draft PR #139 remains unmerged and \`main\` remains unchanged.
