#ifndef DINO_TEST_MOCK_SWITCH_H
#define DINO_TEST_MOCK_SWITCH_H
/* Host-only libnx audout ABI slice. Never installed in the Switch build. */
#include <stddef.h>
#include <stdint.h>
typedef uint32_t u32;
typedef int32_t Result;
typedef struct AudioOutBuffer {
    void *buffer;
    size_t buffer_size;
    size_t data_size;
} AudioOutBuffer;
#define PcmFormat_Int16 2u
#define R_FAILED(result) ((result) < 0)
Result audoutInitialize(void);
u32 audoutGetSampleRate(void);
u32 audoutGetChannelCount(void);
u32 audoutGetPcmFormat(void);
Result audoutStartAudioOut(void);
Result audoutStopAudioOut(void);
void audoutExit(void);
Result audoutGetReleasedAudioOutBuffer(AudioOutBuffer **released, u32 *count);
Result audoutAppendAudioOutBuffer(AudioOutBuffer *buffer);
void armDCacheFlush(void *buffer, size_t size);

/* Deterministic test API for explicit release credits / fault injection. */
void mock_audout_reset(void);
void mock_audout_grant_releases(u32 count);
void mock_audout_inject_bad_release(u32 mode);
/* Test-only delivery order and asynchronous-ready-after-empty stimuli. */
void mock_audout_reverse_release_order(u32 enabled);
void mock_audout_credit_after_next_empty_poll(void);
u32 mock_audout_poll_calls(void);
u32 mock_audout_empty_polls(void);
u32 mock_audout_pending(void);
u32 mock_audout_appended(void);
u32 mock_audout_released(void);
u32 mock_audout_integrity_errors(void);
u32 mock_audout_flushes(void);
u32 mock_audout_stops(void);
u32 mock_audout_page_layout_ok(void);
#endif
