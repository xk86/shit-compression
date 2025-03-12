import math
import os
import subprocess
from platform import system
import warnings
from typing import List
from mdtypes import EssentialMetadataDict, FilterDict

DEBUG = True
DEBUG_LEVEL = 2

def debug_print(msg: str, *args, level: int = 1):
  if DEBUG:
    print(msg, *args)


def get_video_duration(input_file: str) -> float:
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", input_file], stdout=subprocess.PIPE, text=True, check=True)
    return float(result.stdout.strip())

def get_audio_sample_rate(input_file: str) ->float:
    result = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=sample_rate", "-of", "csv=p=0", input_file], stdout=subprocess.PIPE, text=True, check=True)
    return float(result.stdout.strip())

def get_bit_rate(input_file: str, type: str = "video") -> float:
    """Gets or estimates video/audio bitrate from a file.
    Args:
        input_file: Path to the input file.
        type: Type of stream to get bitrate from. Can be "video" or "audio".
    Returns:
        The bitrate in bits per second.
    """
    audio = type[0].lower() == "a"  # only handle video or audio
    typestr = "a:0" if audio else "v:0"  # defaults to video if unknown

    # Try to get bitrate without having to compute
    try:
        metadata_check_br = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", typestr, "-show_entries", "stream=bit_rate", "-of", "csv=p=0", input_file],
            stdout=subprocess.PIPE, text=True, check=True
        ).stdout.strip().split(',')
    except subprocess.CalledProcessError:
        print("Error getting bitrate from metadata")
        metadata_check_br = ["N/A"]

    if metadata_check_br[0] != "N/A":
        return int(metadata_check_br[0])

    # Bitrate wasn't stored in the metadata, so we calculate it
    if metadata_check_br[0] == "N/A":
        fail_cmd = ["ffprobe", "-v", "error", "-select_streams", typestr, "-show_packets", "-show_entries", "packet=size", "-of", "csv=p=0", input_file]
        result = subprocess.run(fail_cmd, stdout=subprocess.PIPE, text=True, check=True).stdout.strip().split('\n')
        total_size = 0
        for size in result:
            # Handle specific output from an opus file
            if ',' in size:
                size = size.split(',')[0]
            total_size += int(size)
        total_size = total_size * 8
        duration = get_video_duration(input_file)
        return total_size / duration

def get_bit_frame_rate(input_file: str) -> float:
  meta = get_video_metadata(input_file)
  return meta["vbitrate"] / meta["fps"]


def get_video_metadata(input_file: str) -> EssentialMetadataDict:
  # This function is a bit messy and can result in bugs if you're not careful about handling codec settings
  video_cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name,width,height,r_frame_rate", "-of", "csv=p=0", input_file]
  audio_cmd = ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_name", "-of", "csv=p=0", input_file]
  format_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=bit_rate", "-of", "csv=p=0", input_file]

  video_output = subprocess.run(video_cmd, stdout=subprocess.PIPE, text=True, check=True).stdout.strip()
  audio_output = subprocess.run(audio_cmd, stdout=subprocess.PIPE, text=True, check=True).stdout.strip()
  format_output = subprocess.run(format_cmd, stdout=subprocess.PIPE, text=True, check=True).stdout.strip()

  video_result = video_output.split(',') if video_output else []
  audio_result = audio_output.split(',') if audio_output else []
  format_result = format_output.split(',') if format_output else []
#
#    if format_result[0] == "N/A":
#      print(video_size)

  vcodec = video_result[0] if len(video_result) > 0 else "h264"
  width = int(video_result[1]) if len(video_result) > 1 and video_result[1].isdigit() else 1920
  height = int(video_result[2]) if len(video_result) > 2 and video_result[2].isdigit() else 1080
  fps_str = video_result[3] if len(video_result) > 3 else "30/1"
  vbitrate = get_bit_rate(input_file)

  num, den = map(int, fps_str.split('/')) if '/' in fps_str else (30, 1)
  fps = num / den

  acodec = audio_result[0] if len(audio_result) > 0 else "aac"
  abitrate = get_bit_rate(input_file, type="audio")

  # Convert vp9 to libvpx-vp9, opus to libopus, and av1 to libvpx-vp9
  if vcodec == "vp9" or vcodec == "av1":
      vcodec = "libvpx-vp9"
  if acodec == "vorbis":
      acodec = "libvorbis"
  if acodec == "opus":
      acodec = "libopus"

  # use the Apple hardware codecs on macOS
  if system() == "Darwin":
    if vcodec == "h264":
      vcodec = "h264_videotoolbox"
    if vcodec == "hevc":
      vcodec = "hevc_videotoolbox"
    if acodec == "aac":
      acodec = "aac_tb"

  vcrf = estimate_crf(vcodec, vbitrate, (width, height), fps)
  acrf = estimate_crf(acodec, abitrate, (1, 1), 1)

  return {"fps": fps, "vcodec": vcodec, "acodec": acodec, "vcrf": vcrf, "acrf": acrf, "vbitrate": vbitrate, "abitrate": abitrate, "resolution": (width, height)}


def estimate_crf(codec: str, bitrate: int, resolution: tuple, fps: float) -> int:
    """
    Estimate CRF dynamically based on the pixels-frame-to-bitrate ratio.
    codec: str (e.g., 'h264', 'hevc', 'vp9', 'av1', 'libvorbis')
    bitrate: int (in bits per second)
    resolution: tuple (width, height)
    fps: float (frames per second)
    """

    # Define CRF range per codec (min_crf = highest quality, max_crf = lowest quality)
    codec_crf_range = {
        'h264': (0, 51), # x264 values
        'hevc': (0, 51),
        'h264_videotoolbox': (1, 100), # apple values
        'hevc_videotoolbox': (1, 100),
        'libvpx-vp9': (0, 63),
        'av1': (0, 63),
        'aac': (1, 14),
        'aac_tb': (1, 14),
        'libopus': (64, 128),
        'libvorbis': (0, 10)
    }

    audio = True if any in ['aac', 'libopus', 'libvorbis'] else False

    if audio:
      fps = 1
      pixels = 1

    if codec not in codec_crf_range:
        raise ValueError(f"Unsupported codec '{codec}'")

    width, height = resolution
    pixels = width * height

    # Compute quality score
    #quality_score = (bitrate / (pixels * fps))  # bits per pixel-frame
    quality_score = (pixels * fps) / bitrate  # Higher means lower quality (fewer bits per pixel-frame)

    #print(f"{codec} Quality score: {quality_score}")
    #if not audio:
    #  print(f"{codec} Resolution: {resolution}, Bitrate: {bitrate}, FPS: {fps}")

    # Apply logarithmic scaling to distribute values evenly
    scaled_score = math.log1p(quality_score)

    #print(f"{codec} Scaled score: {scaled_score}")

    # Normalize scaled score between 0 and 1 based on practical observed ranges
    # Assumption: scaled_score typically varies between -1.0 (excellent) and ~2.0 (poor)
    min_log, max_log = -1,1
    normalized_score = (scaled_score - min_log) / (max_log - min_log)
    debug_print(f"{codec} Normalized score (pre-clamp): {normalized_score}", level=2)
    normalized_score = min(max(normalized_score, 0), 1)  # Clamp 0-1
    debug_print(f"{codec} Normalized score: {normalized_score}", level=2)

    min_crf, max_crf = codec_crf_range[codec]

    # If we're on Apple, the CRF is inverted (higher quality = higher CRF)
    # So we map the normalized score inversely to the CRF range
    if codec == 'h264' or codec == 'hevc':
      estimated_crf = min_crf + (1 - normalized_score) * (max_crf - min_crf)
    else:
      estimated_crf = min_crf + normalized_score * (max_crf - min_crf)
    # Map normalized score inversely to CRF range (higher quality = lower CRF)

    return int(round(estimated_crf))


def compute_quality_score(bitrate: int, resolution: tuple, fps: float) -> float:
    width, height = resolution
    pixels = width * height
    return (pixels * fps) / bitrate  # Higher means lower quality (fewer bits per pixel-frame)

def map_quality_to_crf(codec: str, quality_score: float) -> int:
    codec_crf_ranges = {
        'h264': (0, 51),
        'hevc': (0, 51),
        'libvpx-vp9': (0, 63),
        'av1': (0, 63),
        'aac': (1, 5),
        'libopus': (64, 128),
        'libvorbis': (0, 10),
    }

    min_crf, max_crf = codec_crf_ranges.get(codec, (0, 51))

    # Logarithmic scale ensures smoothness over a large range
    scaled_score = math.log1p(quality_score)

    # Map score inversely across full CRF range
    # Higher quality_score → higher CRF (lower quality)
    normalized_score = scaled_score / (scaled_score + 1)  # smooth 0-1 mapping

    estimated_crf = min_crf + normalized_score * (max_crf - min_crf)

    return int(round(min(max_crf, max(min_crf, estimated_crf))))

def verify_decoded_duration(output_file: str, expected_duration: float):
    """
    Verify the duration of the decoded video segment.

    Parameters:
        output_file (str): Path to the output video file.
        expected_duration (float): Expected duration of the video segment in seconds.

    Raises:
        ValueError: If the actual duration does not match the expected duration.
    """
    actual_duration = get_video_duration(output_file)
    print(f"Verifying decoded duration: expected={expected_duration}, actual={actual_duration}, file={output_file}")
    if not math.isclose(actual_duration, expected_duration, rel_tol=0.01):
        raise ValueError(f"Decoded duration mismatch: expected {expected_duration}, got {actual_duration}")