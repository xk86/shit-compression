# Scene Human Interest Temporal (SHIT) Compression

## Concept
Scene Human Interest Temporal (SHIT) compression is a novel(?) form of compression that aims to compress audio/video files by compressing scenes based on how "interesting" they are to a human viewer.
Scenes that have low interest can be sped up, resulting in a file that, if transcoded with similar settings, should be smaller both in filesize, and in watch/listen time.
The intended goal of this project was initially to compress a movie down to only a few scenes, while still retaining enough information to reconstruct some crude approximation of the source.
Initial testing and design was made for increasing losses on reconstruction, for aesthetic purposes, though the method does seem to work pretty well with mild interest values (0.5-<1).
Tuning and optimizing the compression settings during the transcoding/processing is important, as it's possible to inflate the file on compression.

"Interest" values are currently manually defined, however, there are plenty of heuristics that could be created for determining them, especially if compute power is not a concern.
## Current Implementation
Things are very much a work-in-progress. It's currently platform-specific (hardcoded macos codecs), but it uses ffmpeg on the backend, so with some very minor tweaks, it should be able to work anywhere.
I had ChatGPT make the first rough draft codebase as a proof-of-concept, but have since manually rewritten most of it. (Turns out, hallucinated code only goes so far)
The current version is not working, but thats okay.
Also several glaringly incorrect things.
At the moment, the mshit file is just python code that is eval'd. This is a terrible idea for a metadata format, for what should be obvious reasons. I'll be changing this soon.
Expect things to be rough around the edges, as many things aren't working properly at the moment, and a lot remains to be implemented- even this readme isn't fini

Making the timings work and align is quite difficult.

## Conceptual Overview
In order to be able to reconstruct the video, (and to keep track of what parts we're interested in), we need to store some basic metadata:
For each scene we're not interested in, we need to store the
  Start: the time in seconds that the segment starts
  End: the time in seconds that the segment ends
  Interest: how interested we are in this scene.
Interest values are between 0.01 and 1, where 1 represents we are *completely interested* in that scene (ie, it will not be time-compressed).
If you actually want to be able to reconstruct the video and recognize it afterwards, values around 0.5 or above seem to work fine.

Scenes with an interest value of 1 will be implicitly added, but an idea for future work would be to run in an "inverse" mode where interesting scenes are specified, and the rest of the video has filler segments with some default value.

Additionally, we need to store the original duration of the video we are compressing, so we can reconstruct it later.

The reference "codec" is a wrapper around several ffmpeg commands that:
  Given a metadata file (duration, followed by a list of times and values Scenes of Interest (called "Segments" in the code)), a "source" file (the originally encoded video), and a "target" file (name of the video we are making (or want to decode, if we're decoding)):
    1. Turn our metadata (.mshit) into something useful:
      1. If we're decoding, and the metadata is in reference to the source video (which it should be\*), transform the metadata to be relative to the new video.
      2. Add "identity" scenes (with an interest value of 1) to fill gaps in the metadata.
      3. Align the new list of scenes with the video we're using as input.
    2. Split the file up at those points, along the keyframes.
    3. For each of the split up scenes:
      1. If the scene has an interest value of 1, we don't touch it.
       2. Otherwise, apply the effect filter for the decode/encode pass to speed up/slow down the scene by the interest factor we got from metadata (or computed, for decode).
        - For the encode pass:
          - Note that just because something is theoretically lossless under processing does not mean the final compressed video (and resulting restored video) will be lossless. That is just in reference to how much gets lost between this step, and step 4, as a result of the processing. This algorithm will always fundamentally be lossy, regardless of processing technique.
          - Video: 
            - Presentation Timestamp (PTS) Modification (Fast, theoretically lossless during processing): 
              We can use `setpts` for the video to just double the frame timing.
          - Audio: 
            - Upsampling (Fast, theoretically lossless during processing\*, though not in implementation): 
              Multiplying the audio sample rate of the original video by 1/interest, and resampling the audio to be compatible with the codec will work here. 
              \*Probably possible to use really high sample rates during intermediate processing, then do a two-pass encode that resamples down, to minimize excessive loss.
            - Rubberband (Slow, very lossy at extreme values, but preserves pitch):
              Uses `librubberband` via ffmpeg's `rubberband` filter to compress the time of the audio. Not really noticeable on the encode.
        - For the decode pass:
          - Video: 
            - PTS Modification (Fast, no synthesized frames): 
              We can use `setpts` like the encode pass, which is fast, but very low quality in this case.
            - Motion Interpolation (Slow, surprisingly decent quality):
               We can also use ffmpeg's `minterpolate` filter for motion interpolation, which looks much better (at least for the animated movie trailer I was using as test footage), but runs much, *much* slower. (Might be able to accelerate)
          - Audio:
            - Downsampling (Fast):
              - Uses `asetrate` and `aresample` to slow down the audio.
              - This will always be really crunchy, as we're lowering the sample rate from an already normal one to a much lower rate.
            - Rubberband (Slow, really funny):
              - Uses `rubberband` to give everything that stretched out quality. Might have applications at some point, but it's mostly just aesthetic.
    4. Combine the split up scenes back into one video.
      - This part has several caveats and oddities, mostly owing to the fact that we left the scenes we were interested in with their original codec settings using ffmpeg's `copy` codec.
      - Presently, this problem is solved by controlling the input codec settings, and also matching them as we modify each intermediary scene.
        - This is sub-optimal, and we want to keep the amount of transcoding that's done during the frame/audio manipulation stage- excessively transcoding causes either size inflation, or degradation of quality.
        - A potentially better solution would be to do the speed up, and then encode the whole thing, with the different/fixed codec settings.
          - This two-stage approach is done in the decoding pass already, to mix the framerate down to the original.

  As it's set up right now, the script will take an input file, a target file, and (optionally) an mshit metadata file (see usage below). 

  It will then (if `!skip_encode`) run the encoder on the input file, and save the encoded file to `compressed_[target]`.

  After it saves the encoded file, it will save the original mshit metadata that was used to create it (before any modifications to the timing).

  It will then run the decoder on `compressed_[target]`, and save the decoded file to `restored_[target]`.

## Random Future Optimization Ideas
### Interest Heuristics
Obviously, the most interesting problem, which is why it's up to you, dear reader.
### Transcoding
- Do transcoding in really high framerates, then mix down to settings of original.
- Weigh keyframes more importantly.
### Overall
- Because of how segments are processed, it should be relatively easy to parallelize each part of the algorithm.
- Split the algorithm into VideoSHIT and AudioSHIT, as video and audio compress differently.

## Usage
To run the script, use the following command:

```
python shit.py <input_video> <target_name> [-t metadata_file]
```

- `input_video`: The input video file to be compressed.
- `target_name`: The base name for the output files.
- `-d, --decode`: Only runs the decode pass. Default mode runs encode and decode (for testing).
- `-t, --metadata <file.mshit>`: (Optional) A metadata file containing the duration and scenes.
- `-s, --save_for_next_pass <file.mshit>`: (Optional) Saves timings for the compressed video. Not normally needed for decoding, but helpful for doing multiple passes.
- `-m --minterp <mode>`: (Optional, Decode only). Does motion interpolation. Really slow. Valid modes are `dup`, `blend`, and `mci`. Default is `blend`.

Example:

```
python shit.py input.mp4 output -t timings_of_boring_things.mshit
```