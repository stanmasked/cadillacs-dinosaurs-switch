/* Host-only, ROM-free substitute for libnx audout.
 * Releases are EXTERNAL, explicitly supplied by tests, never guessed.
 * Snapshots guard the active PCM bytes for each unacknowledged buffer.
 */
#include "switch.h"
#include <stdbool.h>
#include <stdint.h>
#include <string.h>

enum { MAX_FLIGHTS=4, PCM_BYTES=3200, PAGE_BYTES=4096 };
typedef struct {
    AudioOutBuffer *buffer;
    uint64_t fingerprint;
} Flight;
static Flight flights[MAX_FLIGHTS];
static u32 pending_count, appended_count, released_count;
static u32 release_credits, pending_deferred_credit;
static u32 fault_mode, integrity_errors;
static u32 flushes, stops, layout_ok;
static u32 poll_calls, empty_polls;
static bool started, reverse_release, credit_after_empty;

static uint64_t fingerprint(const void *base, size_t n) {
    const uint8_t *p=(const uint8_t *)base;
    uint64_t v=UINT64_C(14695981039346656037);
    for (size_t i=0;i<n;++i) {
        v^=p[i];
        v*=UINT64_C(1099511628211);
    }
    return v;
}
static void check_inflight(void) {
    for (u32 i=0;i<pending_count;++i) {
        const AudioOutBuffer *b=flights[i].buffer;
        if (!b || !b->buffer || b->data_size!=PCM_BYTES ||
                fingerprint(b->buffer,b->data_size)!=flights[i].fingerprint)
            ++integrity_errors;
    }
}
void mock_audout_reset(void) {
    memset(flights,0,sizeof(flights));
    pending_count=appended_count=released_count=0;
    release_credits=pending_deferred_credit=0;
    fault_mode=integrity_errors=0;
    flushes=stops=poll_calls=empty_polls=0;
    layout_ok=1;
    started=reverse_release=credit_after_empty=false;
}
void mock_audout_grant_releases(u32 count) {
    /* Test driver advances a tick; the release credited after a
     * previous empty response only becomes visible on this new tick. */
    release_credits=count+pending_deferred_credit;
    pending_deferred_credit=0;
}
void mock_audout_inject_bad_release(u32 mode) { fault_mode=mode; }
void mock_audout_reverse_release_order(u32 enabled) {
    reverse_release=(enabled!=0);
}
void mock_audout_credit_after_next_empty_poll(void) {
    credit_after_empty=true;
}
u32 mock_audout_poll_calls(void) { return poll_calls; }
u32 mock_audout_empty_polls(void) { return empty_polls; }
u32 mock_audout_pending(void) { check_inflight();return pending_count; }
u32 mock_audout_appended(void) { return appended_count; }
u32 mock_audout_released(void) { return released_count; }
u32 mock_audout_integrity_errors(void) {
    check_inflight();
    return integrity_errors;
}
u32 mock_audout_flushes(void) { return flushes; }
u32 mock_audout_stops(void) { return stops; }
u32 mock_audout_page_layout_ok(void) { return layout_ok; }

Result audoutInitialize(void) { return 0; }
u32 audoutGetSampleRate(void) { return 48000; }
u32 audoutGetChannelCount(void) { return 2; }
u32 audoutGetPcmFormat(void) { return PcmFormat_Int16; }
Result audoutStartAudioOut(void) { started=true;return 0; }
Result audoutStopAudioOut(void) { ++stops;started=false;return 0; }
void audoutExit(void) {
    started=false;
    pending_count=0;
    release_credits=pending_deferred_credit=0;
    credit_after_empty=false;
}
Result audoutGetReleasedAudioOutBuffer(AudioOutBuffer **released,u32 *count) {
    static AudioOutBuffer foreign;
    if (!released || !count) return -1;
    ++poll_calls;
    check_inflight();
    *released=NULL;
    *count=0;
    if (fault_mode) {
        u32 mode=fault_mode;
        fault_mode=0;
        if (mode==3) return -1;
        if (mode==1 || mode==2) {
            *released=&foreign;
            *count=(mode==2 ? 2u : 1u);
            return 0;
        }
        return -1;
    }
    if (!started || !release_credits || !pending_count) {
        ++empty_polls;
        /* This fake release becomes available AFTER replying no-count.
         * The unchanged adapter correctly stops polling for this tick. */
        if (credit_after_empty && started && pending_count) {
            pending_deferred_credit=1;
            credit_after_empty=false;
        }
        return 0;
    }
    const u32 index=reverse_release ? pending_count-1u : 0u;
    *released=flights[index].buffer;
    *count=1;
    for (u32 i=index+1u;i<pending_count;++i)
        flights[i-1u]=flights[i];
    flights[--pending_count]=(Flight){0};
    --release_credits;
    ++released_count;
    return 0;
}
Result audoutAppendAudioOutBuffer(AudioOutBuffer *buffer) {
    if (!started || !buffer || !buffer->buffer ||
            pending_count>=MAX_FLIGHTS) return -1;
    check_inflight();
    if (buffer->data_size!=PCM_BYTES || buffer->buffer_size!=PAGE_BYTES ||
            ((uintptr_t)buffer->buffer % PAGE_BYTES)!=0)
        layout_ok=0;
    for (u32 i=0;i<pending_count;++i)
        if (flights[i].buffer==buffer) {
            ++integrity_errors;
            return -1;
        }
    flights[pending_count++]=(Flight){
        buffer,fingerprint(buffer->buffer,buffer->data_size)
    };
    ++appended_count;
    return 0;
}
void armDCacheFlush(void *buffer,size_t bytes) {
    if (!buffer || bytes!=PAGE_BYTES) layout_ok=0;
    ++flushes;
}
