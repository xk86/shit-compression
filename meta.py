import os
import subprocess
import logging

logger = logging.getLogger(__name__)

def add_pass_through_segments(segments, original_duration):
    """Add pass-through segments with intensity 1 between the given segments."""
    new_segments = []
    previous_end = 0

    for seg in segments:
        start, end, interest = seg["start"], seg["end"], seg["interest"]

        # Adjust start to 0 if it's close to 0
        if start < 1:
            start = 0

        # Add pass-through segment if there is a gap between the previous end and the current start
        if start > previous_end:
            new_segments.append({
                "start": previous_end,
                "end": start,
                "interest": 1.0
            })

        # Add the current segment
        new_segments.append(seg)
        previous_end = end

    # Adjust end to original_duration if it's close to original_duration
    if previous_end > original_duration - 1:
        previous_end = original_duration

    # Add pass-through segment if there is a gap between the last segment end and the original duration
    if previous_end < original_duration:
        new_segments.append({
            "start": previous_end,
            "end": original_duration,
            "interest": 1.0
        })
    logger.debug(f"New segments with pass-through: {new_segments}")
    return new_segments


def calculate_compressed_duration(original_duration, segments):
    """Calculate the estimated compressed duration based on the original duration and segment information."""
    compressed_duration = 0
    for seg in segments:
        start, end, interest = seg["start"], seg["end"], seg["interest"]
        segment_duration = end - start
        compressed_segment_duration = segment_duration * interest
        compressed_duration += compressed_segment_duration
        logger.info(f"Segment {start}-{end} with interest {interest}: Original segment duration: {segment_duration}, Compressed segment duration = {compressed_segment_duration}")

    # Add the duration of the parts of the video not covered by segments
    total_segment_duration = sum(seg["end"] - seg["start"] for seg in segments)
    non_segment_duration = original_duration - total_segment_duration
    compressed_duration += non_segment_duration

    return compressed_duration

def calculate_expanded_duration(compressed_duration, segments):
    """Calculate the estimated expanded duration based on the compressed duration and segment information."""
    expanded_duration = 0
    for seg in segments:
        start, end, interest = seg["start"], seg["end"], seg["interest"]
        segment_duration = end - start

        # Relative compressed duration based on interest
        compressed_duration = calculate_compressed_duration(segment_duration, [seg])

        expanded_segment_duration = compressed_duration / interest
        expanded_duration += expanded_segment_duration
        logger.info(f"Segment {start}-{end} with interest {interest}: Compressed segment duration: {compressed_duration}, Expanded segment duration = {expanded_segment_duration}")

    # Add the duration of the parts of the video not covered by segments
    total_segment_duration = sum(seg["end"] - seg["start"] for seg in segments)
    non_segment_duration = compressed_duration - total_segment_duration
    expanded_duration += non_segment_duration

    return expanded_duration


def get_mutated_segments(original_duration, segments):
    """Return a list of mutated segments relative to the times in the compressed video."""
    mutated_segments = []
    current_time = 0

    for seg in segments:
        start, end, interest = seg["start"], seg["end"], seg["interest"]
        segment_duration = end - start
        compressed_segment_duration = segment_duration * interest

        mutated_segments.append({
            "start": current_time,
            "end": current_time + compressed_segment_duration,
            "interest": interest
        })

        current_time += compressed_segment_duration

    # Add the remaining duration as a single segment if there is any
    total_segment_duration = sum(seg["end"] - seg["start"] for seg in segments)
    non_segment_duration = original_duration - total_segment_duration
    if non_segment_duration > 0:
        mutated_segments.append({
            "start": current_time,
            "end": current_time + non_segment_duration,
            "interest": 1.0
        })

    logger.debug(f"Mutated segments: {mutated_segments}")
    return mutated_segments


def adjust_segments_to_keyframes(input_file, segments, temp_dir):
    """Adjust segment times to the closest keyframes."""
    keyframes_file = os.path.join(temp_dir, "keyframes.txt")
    
    # Run ffprobe to get keyframes
    ffprobe_cmd = [
        "ffprobe", "-i", input_file, "-select_streams", "v",
        "-show_packets", "-show_entries", "packet=pts_time,flags", "-of", "csv"
    ]
    
    with open(keyframes_file, "w") as f:
        result = subprocess.run(ffprobe_cmd, stdout=f, stderr=subprocess.PIPE, text=True)
    
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe command failed with return code {result.returncode}")
    
    # Read keyframes from file
    keyframes = []
    with open(keyframes_file, "r") as f:
        for line in f:
            if ",K" in line:  # Filter keyframes
                parts = line.strip().split(",")
                if len(parts) > 1 and parts[1]:
                    try:
                        keyframes.append(float(parts[1]))
                    except ValueError:
                        logger.warning(f"Skipping invalid keyframe timestamp: {parts[1]}")
    
    if not keyframes:
        raise RuntimeError("No keyframes found in the input file.")
    
    logger.info(f"Found {len(keyframes)} keyframes.")
    
    # Adjust segments to the closest keyframes
    adjusted_segments = []
    for seg in segments:
        start = min(keyframes, key=lambda k: abs(k - seg["start"]))
        end = min(keyframes, key=lambda k: abs(k - seg["end"]))
        adjusted_segments.append({"start": start, "end": end, "interest": seg["interest"]})
    
    return adjusted_segments


def write_metadata_file(metadata_file, duration, segments):
    """Write the video metadata to a file."""
    metadata = {
        "duration": duration,
        "segments": segments
    }
    with open(metadata_file, "w") as f:
        f.write(str(metadata))