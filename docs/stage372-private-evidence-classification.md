# Stage372 — fail-closed separation of preflight and native MAME evidence

The owner-only Google Drive report named Stage371_Private_Stage369_Capsule_Preflight.json
(816 bytes) is a **preflight**, not a native execution receipt. It explicitly states
mame_verifyroms_dino_executed=false and windows_process_started=false.
The pinned Stage369 Windows package is a separate owner-only ZIP. Both remain
in Google Drive; their original bytes must not be committed or uploaded to CI.

The source-only module tools/mame0106_private_evidence_gate.py classifies
two distinct JSON types:

- offline_preflight_only — validates the Stage371 preflight schema and
  immutable Stage369 package SHA-256, but **cannot** pass the native gate.
- native_positive_local_self_report or native_negative_local_self_report —
  accepts only the exact Stage371 execution receipt schema and checks its
  internal consistency, including pinned hashes and false playback/Switch flags.
  A positive result is **not** cryptographically authenticated attestation.

Private owner-controlled host commands (JSON file must be outside the checkout):

    python -m tools.mame0106_private_evidence_gate --report "C:\Private\Stage371_Private_Stage369_Capsule_Preflight.json"
    python -m tools.mame0106_private_evidence_gate --report "C:\Private\Stage371-unique-evidence.json" --require-native-positive

The second command returns code **3** if only preflight or a negative runtime
receipt is available, code **2** for invalid evidence or public CI, or code **0**
only for a schema-valid positive **local self-report**. It prints fixed grades,
never private file paths or source contents. A successful grade does not prove
dino.inp playback; that requires a separate real, bounded replay and fresh
owner-only evidence.

All automatic tests use synthetic JSON/receipts, not ROM data. The tests cover
preflight promotion attempts, forged extra keys, wrong hashes, duplicate JSON
keys, malformed/oversized input, symlinks, public CI refusal, negative runtime
outcomes, and unsupported physical-Switch claims. Archive the **real** result
and any derived audit privately in Google Drive under the project Evidence
Archive rules. Public GitHub contains only this source, documentation, and
synthetic tests.
