# Stage329 — require actual playback-counter progress in the synthetic MAME probe

## Purpose

Stage328 made the real MAME 0.106 synthetic Minivader MNG auditable. The next guard is to avoid treating a structurally correct CSV as evidence that playback counters actually advanced.

## Change

The Stage295 probe still requires exactly 24 rows for callbacks 10–33, the expected header, decimal nonnegative fields, monotone cumulative counters, and `playback_words >= first_port_reads` for each row. Stage329 additionally requires both cumulative counters to increase between the first and last row.

The report contains only aggregate deltas and booleans:
- `synthetic_trace_first_port_reads_advanced`
- `synthetic_trace_playback_words_advanced`
- `synthetic_trace_first_port_read_delta`
- `synthetic_trace_playback_word_delta`

Raw CSV rows, input bits, pixels, private paths, and original game material are never printed or uploaded. A structurally valid but static trace now stops with `BLOCKED_SYNTHETIC_PLAYBACK_TRACE_COUNTERS_STATIC`.

## Evidence boundary

This remains a test using an artificial Minivader Z80 fixture and the historical MAME 0.106 executable. Advancing counters demonstrate that the instrumentation observed playback reads over the capture window; they do not prove exact causality between an individual INP record and an individual video frame, authenticate WolfMAME, or establish original Cadillacs and Dinosaurs parity.

The probe continues to mark `exact_input_video_alignment_verified`, `original_gameplay_verified`, and `physical_nintendo_switch_tested` false.
