import os
import subprocess
import shutil
import argparse
from fileops import *
from meta import *
from sys import argv
from lib import get_video_duration, get_video_metadata, get_audio_sample_rate, get_bit_frame_rate, debug_print

# Argument parsing
parser = argparse.ArgumentParser(description="Scene Human Interest Temporal Compression")
parser.add_argument("input_video", help="Input video file")
parser.add_argument("target_name", help="Target name for output files")
parser.add_argument("-t", "--metadata", help="Metadata file containing duration and scenes")
args = parser.parse_args()

# Define input/output filenames
INPUT_VIDEO = args.input_video
COMPRESSED_VIDEO = "compressed_" + args.target_name
RESTORED_VIDEO = "restored_" + args.target_name

VIDEO_CODEC = "h264_videotoolbox"
AUDIO_CODEC = "aac_at"
MINTERP = False

# Split the extension from the filename
TEMP_DIR = "temp_" + os.path.splitext(args.target_name)[0]

# Define segment times (adjust as needed)
# SEGMENTS = [
#     {"start": 0, "end": 600, "interest": 0.5},
# ]

## The commented segments/quotes will be implicitly pass-through segments with interest 1.0
#disinterest_rate = 0.01
#BEE_SEGMENTS = [
#    {"start": 0, "end": 24, "interest": disinterest_rate},  # Speed up the boring dreamworks logo
#    # According to all known laws of aviation, there is no way a bee should be able to fly.
#    {"start": 34, "end": 1395, "interest": disinterest_rate},
#    # Do ya like jazz? - Plate crash
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


def process_segment(input_file, output_file, interest, mode="encode"):
    """Process a video segment by encoding (speed-up) or decoding (slow-down)."""
    # Interest is how interersted we are in a segment.
    # The lower the interest, the more we want to speed up the segment during the encode pass.
    # The higher the interest, the more we want to slow down the segment during the decode pass.

    # The speed factor is the inverse of the interest value.
    # Some filters will take the speed factor as an argument, while others will take the interest value.
    # The filters will be inverse for the encode and decode passes.
    debug_print(f"Processing segment {input_file} with interest {interest} in mode {mode}")
    speed_factor = 1
    speed_filter = ""
    target_framerate = 30
    base_audio_sample_rate = get_audio_sample_rate(input_file)
    source_audio_sr = get_audio_sample_rate(INPUT_VIDEO)
    fr_cmd = []
    if mode == "encode":
      # For the encode pass, the interest will be <1, so speed_factor should be >1
      speed_factor = 1 / interest

      #target_framerate = get_video_metadata(input_file)["fps"] * speed_factor
      target_framerate = get_video_metadata(INPUT_VIDEO)["fps"]
      # Setpts is takes a frequency value, so we use interest.
      # We don't need to motion interpolate on the encode pass, as just increasing the output framerate will be enough, and faster.
      video_filter = f"[0:v]setpts={interest}*PTS[v]"

      # Rubberband version is slower, and preserves the tempo (which isn't necessary, since we're going to slow it down later)
      # It results in some very interesting decode artifacts.
      #audio_filter = f"[0:a]rubberband=tempo={speed_factor}[a]"

      # asetrate version. Increases the sample rate, which speeds the audio up, and then resample down to the source sample rate.
      audio_filter = f"[0:a]asetrate={base_audio_sample_rate}*{speed_factor},aresample={source_audio_sr}[a]" # We can resample to super high quality for processing, but it can cause issues with scenes with interest of 1
      fr_cmd = ["-r", str(target_framerate)]

      speed_filter = f"{video_filter};{audio_filter}"

      # Atempo + asetrate

      #speed_filter = f"[0:v]minterpolate=fps={fps},minterpolate=mi_mode=blend[v];[0:a]rubberband=tempo={speed_factor}[a]"
#    if mode == "encode_final":
#      # Final encode pass where we're reencoding the concatenated segments.
#      target_framerate = get_video_metadata(INPUT_VIDEO)["fps"]
#      audio_filter = f"[0:a]aresample={base_audio_sample_rate}[a]"
#      video_filter = f"[0:v]null[v]"
#      speed_filter = f"{video_filter};{audio_filter}"

    if mode == "decode":
      # For the decode pass, the speed factor will be <1, so we will slow down the video.
      speed_factor = interest # Value to be used to slow down the video
      source_file_fps = get_video_metadata(INPUT_VIDEO)["fps"]
      debug_print(source_file_fps, target_framerate)
      # Note that it's equal to the interest, it's already <1.
      # Uncomment to use setpts instead of minterpolate, much faster, lower quality
      if MINTERP:
        video_filter = f"[0:v]minterpolate=fps={target_framerate},minterpolate=mi_mode=blend,setpts={interest}*PTS[v]"
      else:
        video_filter = f"[0:v]setpts={interest}*PTS[v]"
      audio_filter = f"[0:a]asetrate={base_audio_sample_rate}*{1/interest},aresample={source_audio_sr}[a]"

      # Interpolation based filter to reconstruct frames.
      target_framerate = source_file_fps * speed_factor # for minterpolate
      speed_filter = f"{video_filter};{audio_filter}"
      fr_cmd = ["-r", str(target_framerate)]

    if mode == "decode-final":
      # Final decode pass where we're setting the framerate and audio sample rate back to normal.
      base_audio_sample_rate = get_audio_sample_rate(INPUT_VIDEO)
      target_framerate = get_video_metadata(INPUT_VIDEO)["fps"]
      audio_filter = f"[0:a]aresample={base_audio_sample_rate}[a]"
      speed_filter = f"[0:v]null[v];{audio_filter}"
      fr_cmd = ["-r", str(target_framerate)]

    metadata = get_video_metadata(INPUT_VIDEO)
    debug_print(f"target framerate: {target_framerate}")
    debug_print(metadata)
    debug_print(f"source bfps {INPUT_VIDEO} {get_bit_frame_rate(INPUT_VIDEO)}\ntarget bfps {input_file} {get_bit_frame_rate(input_file)}")

    # If you use high speed intermediaries, there's not as much lost even if it gets dropped down to 30fps.

    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-i", input_file,
        "-filter_complex", speed_filter, #f"[0:v]setpts={setpts_factor}*PTS[v];[0:a]rubberband=tempo={rubberband_factor}[a]",
        "-map", "[v]", "-map", "[a]",
        "-row-mt", "1",  # Enable multi-threading
        "-c:v", metadata["vcodec"],  # Change to a faster video codec
        #"-crf", str(metadata["vcrf"]),  # Adjust quality here
        "-b:v", str(get_bit_frame_rate(INPUT_VIDEO) * target_framerate),  # Adjust bitrate here
        #"-q:v", str(metadata["vcrf"]), # Value 0-100, 0 is worse, 100 is best (h264_videotoolbox)
        "-c:a", metadata["acodec"],  # Change to a faster audio codec (using default for testing)
        "-b:a", str(metadata["abitrate"]),  # Adjust audio bitrate here
        #"-q:a", str(metadata["acrf"]), # 0-14
        #"-ar", "128000",
        "-fflags", "+genpts",
        "-avoid_negative_ts", "make_zero",
        *fr_cmd,
        "-f", "matroska",
        output_file
    ]

    debug_print(f"Running FFmpeg command: {' '.join(ffmpeg_cmd)}")
    result = subprocess.run(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    if result.returncode != 0:
      print(f"FFmpeg stdout: {result.stdout}")
      #print(f"FFmpeg stderr: {result.stderr}")
      raise RuntimeError(f"FFmpeg command failed with return code {result.returncode}")


def concatenate_segments(file_list_path, output_file, metadata):
    """Concatenate processed segments into a final video file without re-encoding."""
    print(f"Concatenating segments in {file_list_path} into {output_file}")
    result = subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", file_list_path,
        "-c:v", "copy",  # Copy codec to avoid re-encoding
        "-c:a", "copy",
        #"-c:a", metadata["acodec"],  
        #"-af", "[0:a]concat=n=1:v=0:a=1[a]",  # Concatenate audio streams
        "-fflags", "+genpts",
        "-avoid_negative_ts", "make_zero",
        "-reset_timestamps", "1",
        #"-copyts",
        "-r", str(metadata["fps"]),  # Set the output framerate
        "-f", "matroska", output_file
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    #print(f"FFmpeg stdout: {result.stdout}")
    #print(f"FFmpeg stderr: {result.stderr}")

    if result.returncode != 0:
      print(f"FFmpeg stdout: {result.stdout}")
      print(f"FFmpeg stderr: {result.stderr}")
      raise RuntimeError(f"FFmpeg command failed with return code {result.returncode}")


def split_video(input_file, segments, prefix):
    """Losslessly split the video file into segments based on the given segment interests."""
    split_files = []
    
    debug_print(f"Splitting video {input_file} into segments:")
    debug_print(segments)

    for i, seg in enumerate(segments):
        start, end = seg["start"], seg["end"]
        duration = end - start
        output_file = f"{prefix}_{i}.mkv"  # Use .mkv extension
        full_output_path = os.path.join(TEMP_DIR, output_file)
        split_files.append(full_output_path)

        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-i", input_file,
            "-ss", str(start), 
            "-t", str(duration),
            "-c", "copy",
            "-reset_timestamps", "1",
            "-fflags", "+genpts",
            "-avoid_negative_ts", "make_zero",
            "-f", "matroska", full_output_path  # Use .mkv format
        ]

        debug_print(f"Running FFmpeg command: {' '.join(ffmpeg_cmd)}")
        result = subprocess.run(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        if result.returncode != 0:
          print(f"FFmpeg stdout: {result.stdout}")
          print(f"FFmpeg stderr: {result.stderr}")
          raise RuntimeError(f"FFmpeg command failed with return code {result.returncode}")

        debug_print(f"Segment {i} split {start} - {end}: {full_output_path}")

    return split_files


def encode_segments(segments_to_encode):
    """Encode (compress) the segments."""
    original_duration = get_video_duration(INPUT_VIDEO)
    split_files = split_video(INPUT_VIDEO, segments_to_encode, "split")
    compressed_segments = []

    print("Beginning encode pass\n", split_files)

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
            print(f"Skipping processing for segment {i} with interest {interest}. Using raw split file.")
        else:
            print(f"Processing segment {i} with interest {interest}. Saving to file {full_compressed_path}")
            process_segment(split_files[i], full_compressed_path, interest, mode="encode")

        compressed_segment_duration = get_video_duration(full_compressed_path)
        original_duration = seg["end"] - seg["start"]
        print(f"Original segment duration: {original_duration}, Compressed segment duration: {compressed_segment_duration}")

    compressed_concat_file = os.path.join(TEMP_DIR, "compressed_list.txt")
    write_file_list(compressed_concat_file, compressed_segments, TEMP_DIR)

    metadata = get_video_metadata(INPUT_VIDEO)
    concatenate_segments(compressed_concat_file, COMPRESSED_VIDEO, metadata)
    print(f"Compression complete: saved as {COMPRESSED_VIDEO}")

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
    split_files = split_video(COMPRESSED_VIDEO, segments, "decode_pre")
    restored_segments = []

    print("Beginning decode pass\n", split_files)
    debug_print(f"Segments: {segments}")

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
            debug_print(f"Skipping processing for segment {i} with interest {interest}. Using raw split file.")
        else:
            debug_print(f"Processing segment {i} with expansion factor {expansion_factor}. Saving to file {full_restored_path}")
            process_segment(split_files[i], full_restored_path, expansion_factor, mode="decode")

        compressed_duration = get_video_duration(split_files[i])
        restored_duration = get_video_duration(full_restored_path)
        print(f"Compressed segment duration: {compressed_duration}, Restored segment duration: {restored_duration}")

    restored_concat_file = os.path.join(TEMP_DIR, "restored_list.txt")
    write_file_list(restored_concat_file, restored_segments, TEMP_DIR)

    metadata = get_video_metadata(INPUT_VIDEO)

    high_fps_video = os.path.join(TEMP_DIR, "high_fps.mkv")
    concatenate_segments(restored_concat_file, high_fps_video, metadata)

    # Reencode to match the framerate to the original video
    process_segment(high_fps_video, RESTORED_VIDEO, 1.0, mode="decode-final")
    print(f"Decompression complete: saved as {RESTORED_VIDEO}")


if __name__ == "__main__":
    original_duration = get_video_duration(INPUT_VIDEO)
    print(f"Original file length: {original_duration} seconds")

    metadata_file = args.metadata if args.metadata else f"{os.path.splitext(INPUT_VIDEO)[0]}.mshit"

    if args.metadata:
        with open(metadata_file, "r") as f:
            metadata = eval(f.read())
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
    print(f"Adjusted segments: {encode_adjusted_segments}, Original segments: {pass_thru}")

    DEBUG = True
    skip_encode = False#False

    if not skip_encode:
      print(get_video_metadata(INPUT_VIDEO))
      compressed_segments = encode_segments(encode_adjusted_segments)
      # Write metadata file after encoding
      write_metadata_file(f"{os.path.splitext(INPUT_VIDEO)[0]}.mshit", original_duration, SEGMENTS)
    if skip_encode:
      pass
      #compresed_segments = [TEMP_DIR + "/compressed_" + str(i) + ".mkv" for i in range(len(SEGMENTS))]
        #compressed_segments = ["temp_hip/compressed_0.mkv", "temp_hip/compressed_1.mkv", "temp_hip/compressed_2.mkv", "temp_hip/compressed_3.mkv", "temp_hip/compressed_4.mkv", "temp_hip/compressed_5.mkv"]
        #compressed_segments = ["temp_trail/compressed_0.mkv", "temp_trail/compressed_1.mkv", "temp_trail/compressed_2.mkv", "temp_trail/compressed_3.mkv"]

        # SHORTBEE dir: temp_SHEE
      #  compressed_segments = ["temp_SHEE/compressed_0.mkv", "temp_SHEE/compressed_1.mkv"]

    estimated_compressed_duration = calculate_compressed_duration(original_duration, encode_adjusted_segments)
    print(f"Estimated compressed duration: {estimated_compressed_duration} seconds")

    ## Calculate estimated expanded duration based on compressed duration
    estimated_expanded_duration = calculate_expanded_duration(estimated_compressed_duration, encode_adjusted_segments)
    print(f"Estimated expanded duration: {estimated_expanded_duration} seconds")

    # Rebase the original segments to be relative to the compressed video
    compressed_duration = get_video_duration(COMPRESSED_VIDEO)
    rebased_segments = get_mutated_segments(compressed_duration, SEGMENTS)
    # Add pass thrus to the rebased segments
    decode_pass_thru = add_pass_through_segments(rebased_segments, compressed_duration)
    # Adjust the rebased segments to keyframes
    decode_adjusted_segments = adjust_segments_to_keyframes(COMPRESSED_VIDEO, decode_pass_thru, TEMP_DIR)
    debug_print(f"Adjusted segments: {decode_adjusted_segments}, Original segments: {decode_pass_thru}")
    decode_segments(decode_adjusted_segments)

    # For testing
    #concatenate_segments("temp/restored_list.txt", RESTORED_VIDEO, get_video_metadata(INPUT_VIDEO))

#process_segment(INPUT_VIDEO, "test.mp4", 0.5, mode="decode")