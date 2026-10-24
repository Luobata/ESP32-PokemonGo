#pragma once
#include "gb_clock.h"
#include "battle_motion.h"

// Preserve Gold's phase ordering, but give our full-size sprite the pre-Johto
// project's ~360 ms absorption instead of compressing it to 9 GBC frames.
// Only this movement is expanded: subsequent effects and cues move together.
#define CAPTURE_ABSORB_START 71u
#define CAPTURE_ABSORB_SOURCE_FRAMES 9u
#define CAPTURE_ABSORB_DISPLAY_FRAMES 22u
#define CAPTURE_ABSORB_EXTRA_FRAMES 13u
static inline uint32_t capture_base_frame_ms(uint16_t source_frame)
{
    unsigned frame=source_frame;
    if(frame>=80u)frame+=CAPTURE_ABSORB_EXTRA_FRAMES;
    else if(frame>CAPTURE_ABSORB_START)
        frame=CAPTURE_ABSORB_START+((frame-CAPTURE_ABSORB_START)*22u+8u)/9u;
    return gb_frames_to_ms((uint16_t)frame);
}
static inline uint32_t capture_base_source_frame(uint32_t ms)
{
    uint32_t frame=gb_frames_from_ms(ms);
    if(frame<CAPTURE_ABSORB_START)return frame;
    if(frame<CAPTURE_ABSORB_START+CAPTURE_ABSORB_DISPLAY_FRAMES)
        return CAPTURE_ABSORB_START+(frame-CAPTURE_ABSORB_START)*9u/22u;
    return frame-CAPTURE_ABSORB_EXTRA_FRAMES;
}

// Stretch movement only: flight, absorption, four bounces, each wobble, and
// breakout/result stars. The gaps between these motions retain their duration.
// Keeping a single forward/inverse map also keeps audio cues in phase on all
// three capture pages, without changing the timing-bar input or catch result.
static const uint16_t CAPTURE_MOTIONS[][2] = {
    {0,37}, {71,80}, {97,225}, {287,322}, {336,371}, {385,420}, {434,470}
};
static inline uint32_t capture_frame_ms(uint16_t source_frame)
{
    uint32_t base=capture_base_frame_ms(source_frame), extra=0;
    for(unsigned i=0;i<sizeof(CAPTURE_MOTIONS)/sizeof(CAPTURE_MOTIONS[0]);++i){
        uint32_t start=capture_base_frame_ms(CAPTURE_MOTIONS[i][0]);
        uint32_t end=capture_base_frame_ms(CAPTURE_MOTIONS[i][1]);
        if(base<=start)break;
        uint32_t motion=(base<end?base:end)-start;
        extra+=battle_motion_ms(motion)-motion;
    }
    return base+extra;
}
static inline uint32_t capture_source_frame(uint32_t ms)
{
    uint32_t extra=0;
    for(unsigned i=0;i<sizeof(CAPTURE_MOTIONS)/sizeof(CAPTURE_MOTIONS[0]);++i){
        uint32_t start=capture_base_frame_ms(CAPTURE_MOTIONS[i][0]);
        uint32_t duration=capture_base_frame_ms(CAPTURE_MOTIONS[i][1])-start;
        uint32_t wall_start=start+extra, wall_duration=battle_motion_ms(duration);
        if(ms<wall_start)break;
        if(ms<wall_start+wall_duration)
            return capture_base_source_frame(start+battle_motion_source_ms(ms-wall_start));
        extra+=wall_duration-duration;
    }
    return capture_base_source_frame(ms-extra);
}

// Include intermediate poses: jumping directly from -4 to +4 looks like a
// fast snap even when the whole shake cycle has the correct duration.
static inline int capture_rock_tilt(unsigned phase)
{
    static const int8_t poses[]={0,-2,-4,-2,0,2,4,2,0};
    return phase<35u ? poses[phase*8u/35u] : 0;
}

#define CAPTURE_RESULT_SOURCE_FRAME 434u
#define CAPTURE_END_SOURCE_FRAME 470u
typedef struct { int x, y, tilt; } capture_ball_pose_t;
// Shared by wild capture, the bug survey and the red Gyarados story. A second
// page must not recreate the same throw/shakes as 64 or 84 callback ticks.
static inline capture_ball_pose_t capture_ball_pose(uint32_t ms)
{
    unsigned t=capture_source_frame(ms);
    capture_ball_pose_t p={120,184,0};
    if(t<37){
        p.x=28+92*t/37;
        p.y=192-86*t/37-80*t*(37-t)/(37*37);
    }else if(t<97)p.y=106;
    else if(t<225){
        unsigned dt=t-97,phase=dt%32,bounce=dt/32;
        if(!bounce)p.y=106+78*phase*phase/(31*31);
        else p.y-=(int)((4-bounce)*12*phase*(32-phase)/(16*16));
    }else if(t>=287&&t<CAPTURE_RESULT_SOURCE_FRAME){
        p.tilt=capture_rock_tilt((t-287)%49);
        p.x+=p.tilt;p.y-=p.tilt<0?-p.tilt/2:p.tilt/2;
    }
    return p;
}
