# Stage377 — immutable private capsule snapshot before native MAME launch

Stage376 introduced a private Windows session receipt, but Stage371's
`native.run()` validated the Stage369 private ZIP and then **reopened the
original path** for extraction. If the source was replaced between those
operations, the checked bytes need not have been the executed bytes.

Stage377 closes this source-path race in
`tools/mame0106_private_native_receipt.py`:

1. Public GitHub Actions and non-Windows execution remain forbidden by
   the same owner-private guards. No private ROM or recording is committed.
2. The normal Stage369 source archive preflight runs first.
3. Before extraction, `_snapshot_private_capsule` copies the source through
   a bounded stream into a fresh, uniquely named owner-private temporary
   directory. The archive is **never** extracted from its mutable source path.
4. The stream is limited to 55 MiB and must equal the **exact** pinned
   Stage369 ZIP SHA-256
   `fa6ff589b109db70c8231bf7713ec50cf5b9a15b58e43bb3b6705bc25e4bd19d`.
5. The copy is flushed, fsynced and hashed again from disk.
6. The existing capsule verifier independently audits the **staged copy**
   against the pinned executable, original ROM, driver XML and PowerShell
   digests plus the precise fixed ZIP inventory, CRC and size constraints.
7. Only the staged copy may provide the four extracted members, and its
   SHA-256 is checked once more after extraction, before PowerShell starts.
8. A mismatch, replacement, invalid member, oversized copy, short read or
   interrupted extraction fails **closed**; no positive runtime receipt can
   be emitted. Temporary staged source bytes are cleaned from the local
   private directory by the context manager.

Public CI uses **synthetic-only** ZIP files and a test-only replacement of
the guard and digest pin. Regression tests verify that a synthetic ZIP
cannot match the real production SHA; that an unaltered synthetic copy can
be staged under a synthetic-only pin; that replacing the ZIP immediately
after the first preflight blocks execution; and that missing revalidation
of the actual snapshot blocks the process.

This is a code-level safety guard, not proof that a private Windows PC has
executed `-verifyroms dino`. The existing receipt is only a local self-report,
not independent cryptographic attestation; it still does not claim
`dino.inp` replay or physical Switch testing.

No new game-derived artifacts are produced by public CI. When the private
Windows host executes, retain the original capsule, session JSON, sealed
manifest, and any future raw/derived outputs **owner-only** in the Google
Drive Project Evidence Archive. Upload first, check permissions and SHA-256
on an independent download, and only then consider private temporary cleanup.
PR #139 remains Draft; no merge into `main`.
