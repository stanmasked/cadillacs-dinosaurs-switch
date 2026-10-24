# Stage403 — architecture-specific Wine DLL path ordering

## Finding

Stage402 placed both `i386-unix` and `x86_64-unix` before parent directories, but applied the same order to both Wine32 and native Wine64 paths. A 64-bit loader must search its matching 64-bit Unix libraries first; otherwise a same-named 32-bit library may be selected before the correct architecture-specific library.

## Change

- Wine32 path order: i386 Unix directory, i386 parent, then amd64 Unix directory and parent.
- Native Wine64 fallback order: amd64 Unix directory, amd64 parent, then i386 Unix directory and parent.
- Replaced the shared-order test with an architecture-specific regression test that checks the exact path list and its placement in the correct workflow block.
- Preserved explicit caller `WINEDLLPATH` values in the guarded launcher.

## Validation status

The change is committed to the existing Draft PR branch. Full regression execution is pending GitHub Actions; this container cannot reach GitHub to clone the repository. Windows ROM-free preflight and PowerShell synthetic smoke checks passed on the previous Stage402 commit, but they do not validate the Stage403 path ordering. The targeted Python, PRoot/QEMU and Wine32 workflows must complete before declaring this fixed.

No original ROM, INP/WLF, extracted game resources, or gameplay captures were added to GitHub.
