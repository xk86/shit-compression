import math
import os
import subprocess
import warnings
from typing import List
from mdtypes import EssentialMetadataDict, FilterDict

def estimate_compression(original_duration: float, encode_filters: List[FilterDict]) -> tuple[float, float]:
    """
    Estimate total video duration after encoding segments.

    Parameters:
        original_duration (float): Duration of original video in seconds.
        encode_filters (list): List of dicts [{"location": start, "duration": duration, "intensity": intensity}, ...]

    Returns:
        compressed_duration (float), compression_ratio (float)
    """
    encoded_time = sum(f["duration"] for f in encode_filters)
    compressed_time = sum(f["duration"] / f["intensity"] for f in encode_filters)

    total_compressed_duration = original_duration - encoded_time + compressed_time
    compression_ratio = total_compressed_duration / original_duration

    print(f"Original duration: {original_duration}, Encoded time: {encoded_time}, Compressed time: {compressed_time}, Total compressed duration: {total_compressed_duration}")

    return total_compressed_duration, compression_ratio

def generate_decode_filters(encode_filters: List[FilterDict], original_duration: float) -> List[FilterDict]:
    """
    Given a list of encoding filter dictionaries, generate the corresponding decoding filters
    that will expand the compressed video back to its original duration.

    Parameters:
        encode_filters (list): List of dicts [{"location": start, "duration": duration, "intensity": intensity}, ...]
        original_duration (float): The original, pre-compression video duration.

    Returns:
        List of dicts: [{"location": start, "duration": duration, "intensity": decode_intensity}, ...]
    """
    decode_filters = []

    for f in encode_filters:
        decode_intensity = 1 / f["intensity"]  # Reverse intensity (slows it back down)
        decode_filters.append({
            "location": f["location"],
            "duration": f["duration"],
            "intensity": decode_intensity
        })

    return decode_filters

def generate_encode_pass_timestamps(filters: List[FilterDict]) -> List[tuple]:
    """
    Generates explicit start and end timestamps ensuring no overlaps for encoding pass.
    
    Parameters:
        filters (list): List of dicts {'location', 'duration', 'intensity'} (intensity > 1.0).

    Returns:
        List of tuples: [(start, end, intensity), ...]
    """
    segments = sorted(
        [(f["location"], f["location"] + f["duration"], f["intensity"])
         for f in filters if f["intensity"] > 1.0],
        key=lambda x: x[0]
    )

    non_overlapping = []
    last_end = -1
    for start, end, intensity in segments:
        if start >= last_end:
            non_overlapping.append((start, end, intensity))
            last_end = end
        else:
            raise ValueError(f"Overlapping segments detected at {start}-{end}")

    return non_overlapping

def validate_filters(filters: List[FilterDict], original_duration: float):
    """
    Validate that the filters do not overlap and are within the video duration.

    Parameters:
        filters (list): List of dicts [{"location": start, "duration": duration, "intensity": intensity}, ...]
        original_duration (float): Duration of original video in seconds.

    Raises:
        ValueError: If filters overlap or are out of bounds.
    """
    last_end = 0
    for f in sorted(filters, key=lambda x: x['location']):
        if f['location'] < last_end:
            raise ValueError(f"Overlapping filters detected at {f['location']}")
        if f['location'] + f['duration'] > original_duration:
            raise ValueError(f"Filter at {f['location']} exceeds video duration")
        last_end = f['location'] + f['duration']

def generate_identity_filters(filters: List[FilterDict], original_duration: float) -> List[FilterDict]:
    """
    Generate identity filters (intensity of 1) for the gaps in the filter list to cover the entire video.

    Parameters:
        filters (list): List of dicts [{"location": start, "duration": duration, "intensity": intensity}, ...]
        original_duration (float): Duration of original video in seconds.

    Returns:
        List of dicts: Complete list of filters covering the entire video.
    """
    identity_filters = []
    last_end = 0
    for f in sorted(filters, key=lambda x: x['location']):
        if f['location'] > last_end:
            identity_filters.append({
                "location": last_end,
                "duration": f['location'] - last_end,
                "intensity": 1.0
            })
        identity_filters.append(f)
        last_end = f['location'] + f['duration']
    if last_end < original_duration:
        identity_filters.append({
            "location": last_end,
            "duration": original_duration - last_end,
            "intensity": 1.0
        })
    return identity_filters

# Function to split and process the video based on specified speed adjustments
def split_and_process_video(input_file: str, output_file: str, filters: List[FilterDict], mode: str = "encode"):
    temp_dir = os.path.join(os.getcwd(), f'temp_processing_{mode}')
    os.makedirs(temp_dir, exist_ok=True)
    duration = get_video_duration(input_file)
    validate_filters(filters, duration)
    filters = generate_identity_filters(filters, duration)
    metadata = get_video_metadata(input_file)
    last_split = 0
    part_index = 0

    concat_list_path = os.path.join(temp_dir, "concat_list.txt")

    if mode == "decode":
        filters = generate_decode_filters(filters, duration)

    with open(concat_list_path, "w") as concat_list:
        for f in sorted(filters, key=lambda x: x['location']):
            location, duration_segment = f["location"], f["duration"]
            intensity = f["intensity"]

            if location > last_split:
                normal_segment = os.path.join(f"part_{part_index}.mp4")
                extract_segment(input_file, last_split, location, normal_segment)
                concat_list.write(f"file '{normal_segment}'\n")
                part_index += 1
                print(f"Normal segment: start={last_split}, end={location}")

            modified_segment = os.path.join(f"part_{part_index}.mp4")
            print(f"{mode.capitalize()} segment: start={location}, end={location + duration_segment}, intensity={intensity}")
            try:
                if intensity == 1.0:
                    # Pass through unchanged segments
                    extract_segment(input_file, location, location + duration_segment, modified_segment)
                else:
                    process_segment(input_file, location, location + duration_segment, modified_segment, intensity, metadata, mode)
                    if mode == "decode":
                        verify_decoded_duration(modified_segment, duration_segment)
            except ValueError as e:
                print(f"Warning: {e}")
            concat_list.write(f"file '{modified_segment}'\n")
            part_index += 1
            last_split = location + duration_segment

        if last_split < duration:
            remaining_segment = os.path.join(f"part_{part_index}.mp4")
            extract_segment(input_file, last_split, duration, remaining_segment)
            concat_list.write(f"file '{remaining_segment}'\n")
            print(f"Remaining segment: start={last_split}, end={duration}")

    concatenate_segments(concat_list_path, output_file, metadata)

def process_segment(input_file: str, start: float, end: float, output_file: str, intensity: float, metadata: EssentialMetadataDict, mode: str = "encode"):
    if intensity == 1.0:
        vf = "null"  # No video filter
        af = "anull"  # No audio filter
    elif mode == "decode":
        vf = f"setpts={intensity}*PTS"  # Slow down video
        af = f"rubberband=tempo={1/intensity}"  # Slow down audio
    else:
        vf = f"setpts={1/intensity}*PTS"  # Speed up video
        af = f"rubberband=tempo={intensity}"  # Speed up audio

    segment_duration = end - start
    print(f"Processing segment: start={start}, end={end}, duration={segment_duration}, intensity={intensity}, mode={mode}")
    print(f"Video filter: {vf}")
    print(f"Audio filter: {af}")

    if segment_duration <= 0:
        warnings.warn(f"Invalid segment duration: start={start}, end={end}, duration={segment_duration}")
        return

    ffmpeg_cmd = [
        "ffmpeg", "-i", input_file, "-ss", str(start), "-to", str(end),
        "-vf", vf,
        "-af", af,
        "-c:v", metadata["vcodec"], "-crf", str(metadata["vcrf"]), "-b:v", str(metadata["vbitrate"]),
        "-c:a", metadata["acodec"], "-b:a", str(metadata["abitrate"]),
        "-r", str(metadata["fps"]),
        "-fflags", "+genpts",
        "-avoid_negative_ts", "make_zero",
        "-y", output_file
    ]
    print(f"Running ffmpeg command: {' '.join(ffmpeg_cmd)}")
    result = subprocess.run(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    print(f"ffmpeg error: {result.stderr}")
    if "Warning" in result.stderr:
        print(f"ffmpeg warning: {result.stderr}")
    result.check_returncode()

    # Verify the duration of the processed segment
    actual_duration = get_video_duration(output_file)
    if mode == "decode":
        expected_duration = end - start
    else:
        expected_duration = (end - start) / intensity
    print(f"Verifying processed segment duration: expected={expected_duration}, actual={actual_duration}, file={output_file}")
    if not math.isclose(actual_duration, expected_duration, rel_tol=0.01):
        warnings.warn(f"Processed segment duration mismatch: expected {expected_duration}, got {actual_duration}")

def get_video_duration(input_file: str) -> float:
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", input_file], stdout=subprocess.PIPE, text=True, check=True)
    return float(result.stdout.strip())

def get_video_metadata(input_file: str) -> EssentialMetadataDict:
    video_cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name,width,height,r_frame_rate", "-of", "csv=p=0", input_file]
    audio_cmd = ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_name", "-of", "csv=p=0", input_file]
    format_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=bit_rate", "-of", "csv=p=0", input_file]

    video_output = subprocess.run(video_cmd, stdout=subprocess.PIPE, text=True, check=True).stdout.strip()
    audio_output = subprocess.run(audio_cmd, stdout=subprocess.PIPE, text=True, check=True).stdout.strip()
    format_output = subprocess.run(format_cmd, stdout=subprocess.PIPE, text=True, check=True).stdout.strip()

    video_result = video_output.split(',') if video_output else []
    audio_result = audio_output.split(',') if audio_output else []
    format_result = format_output.split(',') if format_output else []

    vcodec = video_result[0] if len(video_result) > 0 else "h264"
    width = int(video_result[1]) if len(video_result) > 1 and video_result[1].isdigit() else 1920
    height = int(video_result[2]) if len(video_result) > 2 and video_result[2].isdigit() else 1080
    fps_str = video_result[3] if len(video_result) > 3 else "30/1"
    vbitrate = int(format_result[0]) if len(format_result) > 0 and format_result[0].isdigit() else 200000

    num, den = map(int, fps_str.split('/')) if '/' in fps_str else (30, 1)
    fps = num / den

    acodec = audio_result[0] if len(audio_result) > 0 else "aac"
    abitrate = 48000# Default audio bitrate if not available

    # Convert vp9 to libvpx-vp9, opus to libopus, and av1 to libvpx-vp9
    if vcodec == "vp9" or vcodec == "av1":
        vcodec = "libvpx-vp9"
    if acodec == "vorbis":
        acodec = "libvorbis"
    if acodec == "opus":
        acodec = "libopus"

    vcrf = estimate_crf(vcodec, vbitrate, (width, height), fps)
    acrf = estimate_crf(acodec, abitrate, (1, 1), 1)

    return {"fps": fps, "vcodec": vcodec, "acodec": acodec, "vcrf": vcrf, "acrf": acrf, "vbitrate": vbitrate, "abitrate": abitrate, "resolution": (width, height)}

def extract_segment(input_file: str, start: float, end: float, output_file: str):
    subprocess.run(
        ["ffmpeg", "-i", input_file, "-ss", str(start), "-to", str(end), "-c", "copy", "-y", output_file],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True
    )

def concatenate_segments(concat_list_path: str, output_file: str, metadata: EssentialMetadataDict):
    subprocess.run([
        "ffmpeg", "-f", "concat", "-safe", "0", "-i", concat_list_path,
        "-c:v", metadata["vcodec"], "-crf", str(metadata["vcrf"]), "-b:v", str(metadata["vbitrate"]),
        "-c:a", metadata["acodec"], "-b:a", str(metadata["abitrate"]),
        "-fflags", "+genpts",
        "-avoid_negative_ts", "make_zero",
        "-y", output_file
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)


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
        'h264': (0, 51),
        'hevc': (0, 51),
        'libvpx-vp9': (0, 63),
        'av1': (0, 63),
        'aac': (1, 5),
        'libopus': (64, 128),
        'libvorbis': (0, 10)  # Added libvorbis support
    }

    if codec not in codec_crf_range:
        raise ValueError(f"Unsupported codec '{codec}'")

    width, height = resolution
    pixels = width * height

    # Compute quality score
    quality_score = (bitrate / (pixels * fps))  # bits per pixel-frame

    # Apply logarithmic scaling to distribute values evenly
    scaled_score = math.log1p(quality_score)

    # Normalize scaled score between 0 and 1 based on practical observed ranges
    # Assumption: scaled_score typically varies between -1.0 (excellent) and ~2.0 (poor)
    min_log, max_log = -1.0, 2.0
    normalized_score = (scaled_score - min_log) / (max_log - min_log)
    normalized_score = min(max(normalized_score, 0), 1)  # Clamp 0-1

    # Map normalized score inversely to CRF range (higher quality = lower CRF)
    min_crf, max_crf = codec_crf_range[codec]
    estimated_crf = min_crf + (1 - normalized_score) * (max_crf - min_crf)

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