import os
import subprocess
import shutil
import argparse
from fileops import *
from meta import *
from sys import argv
from avmeta import get_video_duration, get_video_metadata, get_audio_sample_rate, get_bit_frame_rate
from logging_config import logger

# Argument parsing
parser = argparse.ArgumentParser(description="Scene Human Interest Temporal Compression")
parser.add_argument("input_video", help="Input video file")
parser.add_argument("target_name", help="Target name for output files")
parser.add_argument("-t", "--metadata", help="Metadata file containing duration and scenes")
parser.add_argument('-d', '--decode', help="Only run the decoder", action="store_true")
parser.add_argument('-s', '--save_for_next_pass', help="Saves the mutated metadata with the interest times relative to the new compressed file, for doing multiple passes.")
parser.add_argument('-m','--minterp', type=str, help="Turn on motion interpolation during decoding VERY SLOW!) Valid parameters are: 'dup', 'blend', 'mci'. Default: blend", nargs='?', const='blend', choices=['blend','dup','mci'])
args = parser.parse_args()
# https://stackoverflow.com/questions/15301147/python-argparse-default-value-or-specified-value
# Define input/output filenames
INPUT_VIDEO = args.input_video
COMPRESSED_VIDEO = "compressed_" + args.target_name
RESTORED_VIDEO = "restored_" + args.target_name

VIDEO_CODEC = "h264_videotoolbox"
AUDIO_CODEC = "aac_at"

MINTERP = args.minterp

# Split the extension from the filename
TEMP_DIR = "temp_" + os.path.splitext(args.target_name)[0]

# Define segment times (adjust as needed)
# SEGMENTS = t/
#     {"start": 0, "end": 600, "interest": 0.5},
# ]

## The commented segments/quotes will be implicitly pass-through segments with interest 1.0
#disinterest_rate = 0.01
#BEE_SEGMENTS = [
#    {"start": 0, "end": 24, "interest": disinterest_rate},  # Speed up the boring dreamworks logo
#    # According to all known laws of aviation, there is no way a bee should be able to fly.
#    {"start": 34, "end": 1395, "interest": disinterest_rate},
#    # Do ya like jazz?
#    {"start": 1397, "end": 5442, "interest": disinterest_rate}, # The rest of the movie...
#]
#
#SHORTBEE = [
#  {"start": 11, "end": 23, "interest": 0.1},
#  {"start": 25, "end": 66, "interest": 0.1},
#
#]

# Ensure temp directory exists
os.makedirs(TEMP_DIR, exist_ok=True)


def process_segment(input_file, output_file, interest, mode="encode", segments=[]):
    """Process a video segment by encoding (speed-up) or decoding (slow-down)."""
    logger.debug(f"Processing segment {input_file} with interest {interest} in mode {mode}")
    # Interest is how interersted we are in a segment.
    # The lower the interest, the more we want to speed up the segment during the encode pass.
    # The higher the interest, the more we want to slow down the segment during the decode pass.

    # The speed factor is the inverse of the interest value.
    # Some filters will take the speed factor as an argument, while others will take the interest value.
    # The filters will be inverse for the encode and decode passes.
    audio = True 
    speed_factor = 1
    speed_filter = ""
    target_framerate = 30
    base_audio_sample_rate = get_audio_sample_rate(input_file)
    if base_audio_sample_rate == 0:
        logger.info("No audio detected in input file, disabling audio")
        audio = False
    source_audio_sr = get_audio_sample_rate(INPUT_VIDEO)
    fr_cmd = []
    vf_head = "[0:v]"
    vf_tail = "[v]"


    # Encode pass
    if mode == "encode":
      # For the encode pass, the interest will be <1, so speed_factor should be >1
      video_filter = f"{vf_head}"
      speed_factor = 1 / interest
      source_framerate = get_video_metadata(INPUT_VIDEO)["fps"]

      #target_framerate = get_video_metadata(input_file)["fps"] * speed_factor
      # Setpts is takes a frequency value, so we use interest.
      # We don't need to motion interpolate on the encode pass, as just increasing the output framerate will be enough, and faster.
      video_filter += f"setpts={interest}*PTS"
      if DEBUG:
        video_filter += f",drawtext=fontfile=AndaleMono.ttf:text='in encode, fps={source_framerate}, aset fps={source_framerate * speed_factor}':x=(w-text_w)/2:y=(h-text_h)/2:fontsize=48:fontcolor='#4c1659'@0.9"
      

      # Rubberband version is slower, and preserves the tempo (which isn't necessary, since we're going to slow it down later)
      # It results in some very interesting decode artifacts.
      #audio_filter = f"[0:a]rubberband=tempo={speed_factor}[a]"

      # asetrate version. Increases the sample rate, which speeds the audio up, and then resample down to the source sample rate.
      audio_filter = f"[0:a]asetrate={base_audio_sample_rate}*{speed_factor},aresample={source_audio_sr}[a]" # We can resample to super high quality for processing, but it can cause issues with scenes with interest of 1
      fr_cmd = ["-r", str(source_framerate)]


    # Decode pass
    if mode == "decode":
      # For the decode pass, the speed factor will be <1, so we will slow down the video.
      video_filter = f"{vf_head}"
      speed_factor = interest # Value to be used to slow down the video
      source_file_fps = get_video_metadata(INPUT_VIDEO)["fps"]
      logger.debug(f"{str(source_file_fps)} {target_framerate}")

      # Set the target framerate, which will be higher if we're doing motion interpolation
      target_framerate = (source_file_fps * speed_factor) if MINTERP else source_file_fps # for minterpolate

      if MINTERP:
        # https://www.hellocatfood.com/misusing-ffmpegs-motion-interpolation-options/
        # Interesting.
        mi_mode = 'blend'
        if MINTERP == 'mci':
            mi_mode = 'mci:me_mode=bidir:me=tdls,minterpolate=scd=none'

        video_filter += f"minterpolate=fps={target_framerate},minterpolate=mi_mode={mi_mode},setpts={interest}*PTS"
      else:
        video_filter += f"setpts={interest}*PTS"

      if DEBUG:
        video_filter += f",drawtext=fontfile=AndaleMono.ttf:text='in decode, fps={source_file_fps}':x=(w-text_w)/2:y=((h-text_h)/2)-text_h:fontsize=48:fontcolor='#4c1659'@0.9"

      audio_filter = f"[0:a]asetrate={base_audio_sample_rate}*{1/interest},aresample={source_audio_sr}[a]"

      # Interpolation based filter to reconstruct frames.
      fr_cmd = ["-r", str(target_framerate)]

    # Final decode pass
    if mode == "decode-final":
      # Final decode pass where we're setting the framerate and audio sample rate back to normal.
      base_audio_sample_rate = get_audio_sample_rate(INPUT_VIDEO)
      target_framerate = get_video_metadata(INPUT_VIDEO)["fps"]
      audio_filter = f"[0:a]aresample={base_audio_sample_rate}[a]"
      video_filter = f"{vf_head}"
     
      
      video_filter += f"null"

      new_kfs = ",".join([str(seg['end']) for seg in segments])
      fr_cmd = ["-r", str(target_framerate), "-force_key_frames",new_kfs]

    metadata = get_video_metadata(INPUT_VIDEO)
    logger.debug(f"target framerate: {target_framerate}")
    logger.debug(metadata)
    logger.debug(f"source bfps {INPUT_VIDEO} {get_bit_frame_rate(INPUT_VIDEO)}\ntarget bfps {input_file} {get_bit_frame_rate(input_file)}")

    # Add tail at the very end
    video_filter += vf_tail
    # If you use high speed intermediaries, there's not as much lost even if it gets dropped down to 30fps.
    speed_filter = f"{video_filter};{audio_filter}" if audio else video_filter

    # The final command to run
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-i", input_file,
        "-filter_complex", speed_filter, #f"[0:v]setpts={setpts_factor}*PTS[v];[0:a]rubberband=tempo={rubberband_factor}[a]",
        "-map", "[v]", *[s for s in ["-map", "[a]"] if audio],
        "-row-mt", "1",  # Enable multi-threading
        "-c:v", metadata["vcodec"],  # Change to a faster video codec
        #"-crf", str(metadata["vcrf"]),  # Adjust quality here
        "-b:v", str(get_bit_frame_rate(INPUT_VIDEO) * target_framerate),  # Adjust bitrate here
        #"-q:v", str(metadata["vcrf"]), # Value 0-100, 0 is worse, 100 is best (h264_videotoolbox)
        *[s for s in ["-c:a", metadata["acodec"]] if audio],
        *[s for s in ["-b:a", str(metadata["abitrate"])] if audio], 
        #"-q:a", str(metadata["acrf"]), # 0-14
        #"-ar", "128000",
        "-fflags", "+genpts",
        "-avoid_negative_ts", "make_zero",
        *fr_cmd,
        "-f", "matroska",
        output_file
    ]

    logger.info(f"Running FFmpeg command: {' '.join(ffmpeg_cmd)}")
    result = subprocess.run(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    if result.returncode != 0:
        logger.debug(f"FFmpeg stdout: {result.stdout}")
        logger.debug(f"FFmpeg stderr: {result.stderr}")
        raise RuntimeError(f"FFmpeg command failed with return code {result.returncode}")


def concatenate_segments(file_list_path, output_file, metadata, segments=[]):
    """Concatenate processed segments into a final video file without re-encoding."""
    logger.info(f"Concatenating segments in {file_list_path} into {output_file}")
    new_kfs = ",".join([str(seg['end']) for seg in segments])
    logger.debug(f"Forcing keyframes {new_kfs}")
    ffmpeg_cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", file_list_path,
        "-c", "copy",  # Copy codec to avoid re-encoding
        #"-c:a", metadata["acodec"],  
        #"-af", "[0:a]concat=n=1:v=0:a=1[a]",  # Concatenate audio streams
        "-fflags", "+genpts",
        "-avoid_negative_ts", "make_zero",
        "-reset_timestamps", "1",
        #"-copyts",
        "-r", str(metadata["fps"]),  # Set the output framerate
        "-force_key_frames", new_kfs,
        "-f", "matroska", output_file
    ]
    logger.debug(f"Running FFMpeg command: {' '.join(ffmpeg_cmd)}")
    
    result = subprocess.run(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    #print(f"FFmpeg stdout: {result.stdout}")
    #print(f"FFmpeg stderr: {result.stderr}")

    if result.returncode != 0:
        logger.error(f"FFmpeg stdout: {result.stdout}")
        logger.error(f"FFmpeg stderr: {result.stderr}")
        raise RuntimeError(f"FFmpeg command failed with return code {result.returncode}")


def split_video(input_file, segments, prefix):
    """Losslessly split the video file into segments based on the given segment interests."""
    split_files = []
    
    logger.debug(f"Splitting video {input_file} into segments:")
    logger.debug(f"{segments}")

    segment_times = []

    for i, seg in enumerate(segments):
        start, end = seg["start"], seg["end"]
        duration = end - start
        logger.debug(f"Segment {i}, {duration}")
        segment_times.append(str(end))# + duration))
        output_file_template = f"{prefix}_%1d.mkv"  # Use .mkv extension
        full_output_path_template = os.path.join(TEMP_DIR, output_file_template)
        outfile = os.path.join(TEMP_DIR, f"{prefix}_{i}.mkv")
        split_files.append(outfile)

    # Use segment muxer https://stackoverflow.com/questions/44580808/how-to-use-ffmpeg-to-split-a-video-and-then-merge-it-smoothly
    # https://superuser.com/questions/692714/how-to-split-videos-with-ffmpeg-and-segment-times-option
    segment_times = ','.join(segment_times)
    logger.debug(f"{outfile} {seg}")
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        #"-ss", str(start),
        #"-accurate_seek",
        "-i", input_file,
        #"-to", str(end),
        "-map", "0",
        #"-f", "matroska",
        "-c", "copy",
        "-f", "segment",
        "-segment_format", "matroska",
        "-segment_times", segment_times,
        #"-copyts",
        "-reset_timestamps", "1",
        "-fflags", "+genpts",
        "-avoid_negative_ts", "make_zero",
        #outfile, # Use .mkv format
        full_output_path_template,
    ]

    logger.info(f"Running FFmpeg command: {' '.join(ffmpeg_cmd)}")
    result = subprocess.run(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
#logger.debug(f"FFmpeg stdout: {result.stdout}")
#logger.debug(f"FFmpeg stderr: {result.stderr}")

    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg command failed with return code {result.returncode}")

    logger.debug(f"Segments for {input_file} split with times {segments}: {outfile}")

    return split_files


def encode_segments(segments_to_encode):
    """Encode (compress) the segments."""
    original_duration = get_video_duration(INPUT_VIDEO)
    split_files = split_video(INPUT_VIDEO, segments_to_encode, "split")
    compressed_segments = []

    logger.info(f"Beginning encode pass\n{split_files}")

    for i, seg in enumerate(segments_to_encode):
        interest = seg["interest"]

        # Dynamically infer the filename extension
        _, ext = os.path.splitext(split_files[i])
        compressed_file = f"compressed_{i}{ext}"
        full_compressed_path = os.path.join(TEMP_DIR, compressed_file)
        compressed_segments.append(full_compressed_path)

        if interest == 1.0:
            # Skip processing and use the raw split file
            shutil.copy(split_files[i], full_compressed_path)
            logger.info(f"Skipping processing for segment {i} with interest {interest}. Using raw split file.")
        else:
            logger.info(f"Processing segment {i} with interest {interest}. Saving to file {full_compressed_path}")
            process_segment(split_files[i], full_compressed_path, interest, mode="encode")

        compressed_segment_duration = get_video_duration(full_compressed_path)
        original_duration = seg["end"] - seg["start"]
        logger.info(f"Original segment duration: {original_duration}, Compressed segment duration: {compressed_segment_duration}")

    compressed_concat_file = os.path.join(TEMP_DIR, "compressed_list.txt")
    write_file_list(compressed_concat_file, compressed_segments, TEMP_DIR)

    metadata = get_video_metadata(INPUT_VIDEO)
    concatenate_segments(compressed_concat_file, COMPRESSED_VIDEO, metadata, segments=get_mutated_segments(segments_to_encode))
    logger.info(f"Compression complete: saved as {COMPRESSED_VIDEO}")

    return compressed_segments


def decode_segments(segments):
    """Decode (expand) the segments."""
    #original_duration = get_video_duration(INPUT_VIDEO)

    # This code is now done before calling this function
    # We need to adjust the segment times to first be relative to the compressed video.
    # Then we adjust those times to the closest keyframes.
    #segments_with_pass_through = add_pass_through_segments(segments, original_duration)
    #mutated_segments = get_mutated_segments(original_duration, segments_with_pass_through)
    #adjusted_segments = adjust_segments_to_keyframes(COMPRESSED_VIDEO, mutated_segments)

    #adjusted_segments = mutated_segments
    restored_segments = []

    logger.debug(f"Segments: {segments}")
    split_files = split_video(COMPRESSED_VIDEO, segments, "decode_pre")
    logger.info(f"Beginning decode pass\n{split_files}")

    for i, seg in enumerate(segments):
        interest = seg["interest"]
        expansion_factor = 1 / interest  # Decompression factor (to restore timing)

        # Dynamically infer the filename extension
        _, ext = os.path.splitext(COMPRESSED_VIDEO)
        restored_file = f"restored_{i}{ext}"
        full_restored_path = os.path.join(TEMP_DIR, restored_file)
        restored_segments.append(full_restored_path)

        if interest == 1.0:
            # Skip processing and use the raw split file
            shutil.copy(split_files[i], full_restored_path)
            logger.debug(f"Skipping processing for segment {i} with interest {interest}. Using raw split file.")
        else:
            logger.debug(f"Processing segment {i} with expansion factor {expansion_factor}. Saving to file {full_restored_path}")
            process_segment(split_files[i], full_restored_path, expansion_factor, mode="decode")

        compressed_duration = get_video_duration(split_files[i])
        restored_duration = get_video_duration(full_restored_path)
        logger.info(f"Compressed segment duration: {compressed_duration}, Restored segment duration: {restored_duration}")

    restored_concat_file = os.path.join(TEMP_DIR, "restored_list.txt")
    write_file_list(restored_concat_file, restored_segments, TEMP_DIR)

    metadata = get_video_metadata(INPUT_VIDEO)

    high_fps_video = os.path.join(TEMP_DIR, "high_fps.mkv")
    concatenate_segments(restored_concat_file, high_fps_video, metadata, segments=segments)

    # Reencode to match the framerate to the original video
    process_segment(high_fps_video, RESTORED_VIDEO, 1.0, mode="decode-final", segments=segments)
    logger.info(f"Decompression complete: saved as {RESTORED_VIDEO}")


if __name__ == "__main__":
    original_duration = get_video_duration(INPUT_VIDEO)
    logger.info(f"Original file length: {original_duration} seconds")

    metadata_file = args.metadata if args.metadata else f"{os.path.splitext(INPUT_VIDEO)[0]}.mshit"

    if args.metadata:
        with open(metadata_file, "r") as f:
            metadata = eval(f.read()) # TODO: Not this... this is terrible
            original_duration = metadata["duration"]
            SEGMENTS = metadata["segments"]
    else:
        SEGMENTS = [
            {"start": 0, "end": 120, "interest": 0.5},
        ]

#    if INPUT_VIDEO == "bee_movie.mkv":
#        SEGMENTS = BEE_SEGMENTS
#    if INPUT_VIDEO == "SHORTBEE.mkv":
#        SEGMENTS = SHORTBEE

    # Add pass-thru segments, then adjust segments to keyframes
    pass_thru = add_pass_through_segments(SEGMENTS, original_duration)
    encode_adjusted_segments = adjust_segments_to_keyframes(INPUT_VIDEO, pass_thru, TEMP_DIR)
    logger.info(f"Adjusted segments: {encode_adjusted_segments}, Original segments: {pass_thru}")



    
    DEBUG = False
    skip_encode = False
    if args.decode:
       skip_encode = True

    if not skip_encode:
        logger.info(get_video_metadata(INPUT_VIDEO))
        compressed_segments = encode_segments(encode_adjusted_segments)
        #compressed_segments = encode_segments(pass_thru)
        # Write metadata file after encoding
        write_metadata_file(f"{os.path.splitext(INPUT_VIDEO)[0]}.mshit", original_duration, SEGMENTS)
    if skip_encode:
        #if INPUT_VIDEO == "compressed_SHORBE.mkv" or INPUT_VIDEO == "restored_SHORBE.mkv":
        COMPRESSED_VIDEO = INPUT_VIDEO
        pass
        #compresed_segments = [TEMP_DIR + "/compressed_" + str(i) + ".mkv" for i in range(len(SEGMENTS))]
        #compressed_segments = ["temp_hip/compressed_0.mkv", "temp_hip/compressed_1.mkv", "temp_hip/compressed_2.mkv", "temp_hip/compressed_3.mkv", "temp_hip/compressed_4.mkv", "temp_hip/compressed_5.mkv"]
        #compressed_segments = ["temp_trail/compressed_0.mkv", "temp_trail/compressed_1.mkv", "temp_trail/compressed_2.mkv", "temp_trail/compressed_3.mkv"]
        #if INPUT_VIDEO == "compressed_SHORBE.mkv":
           

        # SHORTBEE dir: temp_SHEE
        #  compressed_segments = ["temp_SHEE/compressed_0.mkv", "temp_SHEE/compressed_1.mkv"]

    #estimated_compressed_duration = calculate_compressed_duration(original_duration, encode_adjusted_segments)
    #logger.info(f"Estimated compressed duration: {estimated_compressed_duration} seconds")

    ## Calculate estimated expanded duration based on compressed duration
    #estimated_expanded_duration = calculate_expanded_duration(estimated_compressed_duration, encode_adjusted_segments)
    #logger.info(f"Estimated expanded duration: {estimated_expanded_duration} seconds")

    # Rebase the original segments to be relative to the compressed video
    compressed_duration = get_video_duration(COMPRESSED_VIDEO)
    # Add pass thrus to the rebased segments
    decode_pass_thru_segments = add_pass_through_segments(SEGMENTS, compressed_duration)
    rebased_segments = get_mutated_segments(decode_pass_thru_segments)
    # Adjust the rebased segments to keyframes
    decode_adjusted_segments = adjust_segments_to_keyframes(COMPRESSED_VIDEO, rebased_segments, TEMP_DIR)
    logger.debug(f"Adjusted segments: {decode_adjusted_segments}, Original segments: {decode_pass_thru_segments}")
    decode_segments(decode_adjusted_segments)

    if args.save_for_next_pass:
        write_metadata_file(f"{os.path.splitext(args.save_for_next_pass)[0]}.mshit",
                            )

    # For testing
    #concatenate_segments("temp/restored_list.txt", RESTORED_VIDEO, get_video_metadata(INPUT_VIDEO))

#process_segment(INPUT_VIDEO, "test.mp4", 0.5, mode="decode")