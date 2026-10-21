# Stage286 — private, bounded windowed INP playback and MNG capture

Stage285's orchestration now has a bounded frame-window mode. The historical
MAME 0.106 source patch adds two options:

- `-mngstartframe N`: zero-based candidate video-callback index where capture starts.
- `-mngframes N`: maximum number of MNG frames to write (2–3601 in the runner).

The patch is included as `mame0106-windowed-mng-capture.patch`; CI applies it
to the source-pinned upstream tree, builds the Windows runtime, and checks
that both options appear in `-showconfig`. This is a **custom-patched MAME
0.106 runtime**, not an attested WolfMAME binary.

## Required private workstation inputs

Keep these outside the public repository:

- The custom-patched MAME 0.106 executable built from the Stage286 artifact.
- An authorized ROM directory containing the expected dino ROM set.
- The paired original `dino.inp` and `dino.wlf` files.

The runner calls the read-only Stage279 gate first. It refuses to start if
the recording isn't identified as the WolfMAME 0.106 family, the executable's
help does not report MAME 0.106, or ROM verification fails. The original
recording files, ROM files and captured frames must never be uploaded to
public CI or committed to the repository.

## Bounded capture command

On a private Windows workstation, from a Python environment containing the
repository's tools, request a 1,200-frame candidate window beginning at frame
36,000:

    python tools/wolfmame0106_private_mng_capture.py ^
      --emulator C:\private\mame0106.exe ^
      --rom-dir C:\private\roms ^
      --inp C:\private\recordings\dino.inp ^
      --wlf C:\private\recordings\dino.wlf ^
      --start-frame 36000 --frames 1200 --seconds 1800 ^
      --capture-out C:\private\audits\stage286.mng ^
      --out C:\private\audits\stage286.json

This is a generic example; substitute a candidate window selected by the
private, local input analysis. The runner validates that
`start_frame + frames` stays within the recorded input-record count, then
runs playback from the beginning with `-nothrottle` and
`-frames_to_run (start_frame + frames)`. The patched video writer suppresses
MNG writes before the requested window and closes the MNG after the requested
frame count. The emulator still has to emulate the frames leading up to the
window, so runtime depends on the machine. The timeout ceiling is 30 minutes to permit windows late in a long recording.

In historical Windows MAME, `FILETYPE_MOVIE` writes in the current working
directory and appends `.mng`. The runner uses an isolated temporary working
directory, copies the original INP/WLF byte-for-byte, discards raw stdout and
stderr, audits the candidate, and removes temporary files after the run.
The optional retained MNG and JSON receipt are exclusive private files with
mode 0600 and must be outside the repository.

## Evidence semantics and limits

The report distinguishes:

- recording/version/ROM preflight;
- whether the process spawned, exited zero or timed out;
- MNG integrity, exact candidate frame count and adjacent-pixel continuity;
- the requested frame offset and whether the request lies within the recording.

A matching frame count does **not** prove the capture began on the corresponding
INP record. The frame offset is a candidate video-callback index; startup,
render scheduling and the historical OSD may introduce an offset. The tool
therefore always reports `capture_start_frame_verified=false` and
`input_video_alignment_verified=false`.

Even `CANDIDATE_MNG_VALID_PLAYBACK_UNAUTHENTICATED` is not called a successful
original replay. It does not prove binary provenance, complete original
recording playback, exact input/video alignment, original gameplay parity or
physical Nintendo Switch execution.

## ROM-free tests

    python -m unittest discover -s tests -p 'test_wolfmame0106_private_mng_capture.py' -v

Tests use artificial input placeholders and tiny synthetic RGB MNG files.
No copyrighted game assets or actual input recordings are needed or allowed
in public CI. This PR stacks on Stage285 and changes neither main nor approved
cover assets.
