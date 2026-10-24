# Stage379 — offline audit of an owner-private Windows MAME session

## State and purpose

On 2026-10-24 the previous Stage378 revision passed all five GitHub
checks, including native **ROM-free** Windows MAME 0.106, synthetic
Windows PowerShell, Python, Switch bootstrap and ROM privacy. No
real `MAME 0.106 -verifyroms dino` private Windows receipt was found
in the project's `03_Aggregate_Reports` Google Drive archive; archived
ROM-free status files and the original Stage369 private capsule do not
provide this missing observation.

A Stage376 private run may eventually create two files:

- `stage376-native-receipt.json` — a source-pinned local process self-report
- `stage376-session-manifest.json` — receipt byte count, SHA-256, grade,
  pinned Stage369 capsule SHA, and explicit limits of what was *not* tested

Until now those two records were not independently audited *together* on
a subsequent machine. Stage379 implements a source-only command:
`tools/mame0106_private_session_audit.py`.

## Audit's strict checks

The auditor needs no game data and cannot start MAME:

1. Refuses running on GitHub Actions, in a public Git checkout, or through
   linked/reparse parent directories. Owner-only private reports only.
2. Refuses extra/missing files; expects exactly the two Stage376 JSON records.
3. Reads each file through a single opened descriptor, capped at 4 KiB,
   comparing type, size and file identity before and after reading.
4. Rejects symlinks/reparse points, duplicate JSON keys, non-finite JSON,
   malformed UTF-8, extra/missing schema fields and changed receipt bytes.
5. Compares the exact receipt length and SHA-256 to the manifest and
   independently validates the embedded Stage369 capsule SHA-256.
6. Uses the Stage372/373 native runtime receipt classifier, refusing
   malformed or unsupported claims (including INP playback or hardware).
7. Requires the manifest's positive/negative grade to agree exactly with
   the classified receipt, and requires a valid UTC manifest timestamp
   not earlier than the local receipt's completion time.
8. Returns a *local-self-report* evidence grade, never independent
   cryptographic attestation. `--require-native-positive` returns 3 if
   a valid **negative** report is supplied; malformed evidence returns 2.

Private owner-host usage **only after a genuine Windows session exists**:

```powershell
python -m tools.mame0106_private_execution_session --capsule "C:\Private\Stage369_MAME0106_Private_Windows_Verify_Capsule.zip" --session-dir "C:\Private\Stage376-unique-session"
python -m tools.mame0106_private_session_audit --session-dir "C:\Private\Stage376-unique-session" --require-native-positive
```

These paths are examples; the original archive lives in private Drive, not
in public GitHub. Stage379 **does not** create or claim a real native receipt.

## Retention contract

After the real owner-controlled run, store the receipt, manifest, any
private diagnostic evidence and SHA-256 readback checks in Google Drive's
owner-only Cadillacs and Dinosaurs Remake Project Evidence Archive, under
`03_Aggregate_Reports`. Retain originals separately unchanged. Never
upload an original ROM, INP/WLF, extracted resource, or game trace to public
GitHub Actions. Any private report is a local unauthenticated self-report;
a successful format audit alone is not proof of independent execution.
PR #139 stays Draft and `main` is unchanged.

The accompanying **synthetic-only** tests intentionally alter receipt
bytes, independently recompute forged manifest hashes, forge positive grades,
add files, use symlinks, insert duplicate JSON keys, and verify that
malformed/negative evidence cannot pass the positive gate. No ROM/MAME files
enter public CI.
