#ifndef DINO_GUEST_COUNTER_PROBE_H
#define DINO_GUEST_COUNTER_PROBE_H
#include <stdio.h>

/* Standalone, ROM-free guest selftest. Never maps HID/controller buttons.
 * Writes a bounded diagnostic CSV to a caller-provided stream.
 * Returns 1 on successful writes, 0 on failure or NULL.
 */
int dino_guest_counter_probe(FILE *stream);
#endif
