#include "cps1_sequence.h"
#include <string.h>

/* CRC32/IEEE (same polynomial and initial/final xor as Python zlib.crc32). */
static uint32_t crc32_region(const uint8_t *data, size_t count) {
    uint32_t crc=0xffffffffu;
    for (size_t i=0; i<count; ++i) {
        crc ^= data[i];
        for (unsigned b=0; b<8; ++b)
            crc=(crc>>1) ^ (0xedb88320u & (0u-(crc&1u)));
    }
    return ~crc;
}
static uint16_t le16(const uint8_t *p) {
    return (uint16_t)(p[0] | (uint16_t)(p[1]<<8));
}
static uint32_t le32(const uint8_t *p) {
    return ((uint32_t)p[0]) | ((uint32_t)p[1]<<8) |
           ((uint32_t)p[2]<<16) | ((uint32_t)p[3]<<24);
}

bool cps1_sequence_decode(const uint8_t *data, size_t length,
                          Cps1Sequence *out) {
    if (!data || !out || length < CPS1_SEQUENCE_HEADER_BYTES ||
        length > CPS1_SEQUENCE_MAX_BYTES || memcmp(data,"CPS1SEQ1",8))
        return false;
    const unsigned count=le16(data+8), fps=le16(data+10);
    if (count<1 || count>CPS1_SEQUENCE_MAX_FRAMES ||
        fps<1 || fps>60 || le32(data+16)!=0 ||
        length!=CPS1_SEQUENCE_HEADER_BYTES+(size_t)count*CPS1_SCENE_FILE_BYTES)
        return false;
    if (crc32_region(data+CPS1_SEQUENCE_HEADER_BYTES,
                     length-CPS1_SEQUENCE_HEADER_BYTES)!=le32(data+12))
        return false;
    /* Verify each embedded CPS1SCN1 header/CRC before accepting a sequence.
     * Avoid allocating a ~65 KiB decoded scene once per frame: checks here
     * match cps1_scene_decode's framing, including reserved header word. */
    for (unsigned i=0; i<count; ++i) {
        const uint8_t *frame=data+CPS1_SEQUENCE_HEADER_BYTES+
                             (size_t)i*CPS1_SCENE_FILE_BYTES;
        if (memcmp(frame,"CPS1SCN1",8) ||
            le32(frame+8)!=CPS1_SCENE_PAYLOAD_BYTES ||
            crc32_region(frame+16,CPS1_SCENE_PAYLOAD_BYTES)!=le32(frame+12) ||
            frame[16+4+12+3]!=0) /* reserved byte after 3 flags */
            return false;
    }
    Cps1Sequence accepted={data,(uint16_t)count,(uint16_t)fps};
    *out=accepted;
    return true;
}

bool cps1_sequence_frame(const Cps1Sequence *sequence,unsigned index,
                         Cps1Scene *out) {
    if (!sequence || !sequence->blob || !out || index>=sequence->frame_count)
        return false;
    const uint8_t *frame=sequence->blob+CPS1_SEQUENCE_HEADER_BYTES+
                         (size_t)index*CPS1_SCENE_FILE_BYTES;
    return cps1_scene_decode(frame,CPS1_SCENE_FILE_BYTES,out);
}

void cps1_playback_init(Cps1Playback *playback) {
    if (!playback) return;
    *playback=(Cps1Playback){0,0,2,false};
}

bool cps1_playback_advance(Cps1Playback *playback,
                           const Cps1Sequence *sequence,uint32_t ticks60) {
    if (!playback || !sequence || sequence->frame_count==0 ||
        playback->paused || !ticks60) return false;
    unsigned speed=playback->speed_num;
    if (speed!=1 && speed!=2 && speed!=4) return false;
    /* uint64_t handles even anomalously large elapsed tick values. */
    uint64_t total=(uint64_t)playback->remainder+
                   (uint64_t)ticks60*sequence->fps*speed;
    uint64_t frames=total/120u;
    playback->remainder=(uint32_t)(total%120u);
    if (!frames) return false;
    playback->index=(uint32_t)((playback->index+(frames%sequence->frame_count))%
                               sequence->frame_count);
    return true; /* even a whole-number loop advances the animation clock */
}

bool cps1_playback_step(Cps1Playback *playback,
                        const Cps1Sequence *sequence,int direction) {
    if (!playback || !sequence || sequence->frame_count==0 || direction==0)
        return false;
    unsigned n=sequence->frame_count;
    if (direction>0) playback->index=(playback->index+1)%n;
    else playback->index=(playback->index+n-1)%n;
    playback->remainder=0;
    playback->paused=true;
    return true;
}

void cps1_playback_speed(Cps1Playback *playback,int direction) {
    if (!playback) return;
    unsigned speed=playback->speed_num;
    if (speed!=1 && speed!=2 && speed!=4) speed=2;
    if (direction<0 && speed>1) speed/=2;
    if (direction>0 && speed<4) speed*=2;
    playback->speed_num=speed;
}
