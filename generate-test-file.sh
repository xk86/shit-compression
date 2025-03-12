#!/bin/zsh

# https://notes.mark.himsley.org/FFmpeg/creating_test_signal_files.html
# https://superuser.com/questions/724391/how-to-generate-a-sine-wave-with-ffmpeg
ffmpeg -y \
       -f lavfi -i testsrc=duration=180:size=1280x720:rate=60 \
       -f lavfi -i sine=frequency=432:duration=180 \
       -i barry.webp \
       -filter_complex "[2:v]scale=100:100[overlay]; \
                        [0:v][overlay]overlay=x='(W-100)*(0.5+0.5*cos(PI*t/2))': \
                                              y='(H-100)*(0.5+0.5*sin(PI*t/3))'[v1]; \
                        [v1]drawtext=text=%{n}:fontsize=72:r=60:x=(w-tw)/2:y=h-(2*lh):fontcolor=white:box=1:boxcolor=0x00000099[vfinal]" \
       -force_key_frames "60,120,180" \
       -map "[vfinal]" -map 1:a \
       -af "volume=-18dB" \
       -c:a libopus \
       testing_file.mkv

       #-c:v h264_videotoolbox \
       #-vf "vdrawtext=text=%{n}:fontsize=72:r=60:x=(w-tw)/2: y=h-(2*lh):fontcolor=white:box=1:boxcolor=0x00000099" \


       # ChatGPT's first attempt at a bouncing logo. Not bad
       #-filter_complex "[2:v]scale=100:100[overlay]; \
       #                 [0:v][overlay]overlay=x=(W-100)*abs(cos(2*PI*t)):y=(H-100)*abs(sin(2*PI*t))[v1]; \
       #                 [v1]drawtext=text=%{n}:fontsize=72:r=60:x=(w-tw)/2:y=h-(2*lh):fontcolor=white:box=1:boxcolor=0x00000099[vfinal]" \

       # Second attempt didn't work...
       #-filter_complex "[2:v]scale=100:100[overlay]; \
       #                 [0:v]overlay=x='mod(t*200, W-100)':y='mod(t*150, H-100)'[v1]; \
       #                 [v1]drawtext=text=%{n}:fontsize=72:r=60:x=(w-tw)/2:y=h-(2*lh):fontcolor=white:box=1:boxcolor=0x00000099[vfinal]" \

       # Third is better!
       #-filter_complex "[2:v]scale=100:100[overlay]; \
       #                 [0:v][overlay]overlay=x='W/2 + (W/2-100)*abs(cos(2*PI*t/5))':y='H/2 + (H/2-100)*abs(sin(2*PI*t/7))'[v1]; \
       #                 [v1]drawtext=text=%{n}:fontsize=72:r=60:x=(w-tw)/2:y=h-(2*lh):fontcolor=white:box=1:boxcolor=0x00000099[vfinal]" \