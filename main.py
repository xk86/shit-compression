import subprocess
import os
import tempfile

def split_and_process_video(input_file, output_file, filters):
    temp_dir = tempfile.mkdtemp()
    segments = []
    
    # Get original frame rate
    fps = get_video_fps(input_file)
    duration = get_video_duration(input_file)
    
    last_split = 0
    part_index = 0
    for f in sorted(filters, key=lambda x: x['location']):
        location = f["location"]
        duration_segment = f["duration"]
        intensity = f["intensity"]
        
        # Extract and decode raw frames
        raw_frames_dir = os.path.join(temp_dir, f"frames_{part_index}")
        os.makedirs(raw_frames_dir, exist_ok=True)
        
        if location > last_split:
            normal_segment = os.path.join(temp_dir, f"part_{part_index}.mp4")
            extract_raw_frames(input_file, last_split, location, raw_frames_dir, fps)
            encode_video(raw_frames_dir, fps, normal_segment)
            segments.append(normal_segment)
            part_index += 1
        
        # Process affected segment with modified speed
        modified_segment = os.path.join(temp_dir, f"part_{part_index}.mp4")
        modified_fps = fps * intensity
        extract_raw_frames(input_file, location, location + duration_segment, raw_frames_dir, fps)
        encode_video(raw_frames_dir, modified_fps, modified_segment, intensity)
        segments.append(modified_segment)
        part_index += 1
        last_split = location + duration_segment
    
    # Extract and process remaining frames if needed
    if last_split < duration:
        remaining_segment = os.path.join(temp_dir, f"part_{part_index}.mp4")
        raw_frames_dir = os.path.join(temp_dir, f"frames_{part_index}")
        os.makedirs(raw_frames_dir, exist_ok=True)
        extract_raw_frames(input_file, last_split, duration, raw_frames_dir, fps)
        encode_video(raw_frames_dir, fps, remaining_segment)
        segments.append(remaining_segment)
    
    # Concatenate processed video segments
    concat_file = os.path.join(temp_dir, "concat_list.txt")
    with open(concat_file, "w") as f:
        for segment in segments:
            f.write(f"file '{segment}'\n")
    
    cmd = ["ffmpeg", "-f", "concat", "-safe", "0", "-i", concat_file, "-c", "copy", output_file]
    subprocess.run(cmd, check=True)

def get_video_fps(input_file):
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", input_file]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, check=True)
    num, den = map(int, result.stdout.strip().split("/"))
    return num / den

def get_video_duration(input_file):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", input_file]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, check=True)
    return float(result.stdout.strip())

def extract_raw_frames(input_file, start, end, output_dir, fps):
    cmd = [
        "ffmpeg", "-i", input_file, "-ss", str(start), "-to", str(end), "-vf", f"fps={fps}",
        os.path.join(output_dir, "frame_%04d.png")
    ]
    subprocess.run(cmd, check=True)

def encode_video(frames_dir, fps, output_file, intensity=1.0):
    cmd = [
        "ffmpeg", "-framerate", str(fps), "-i", os.path.join(frames_dir, "frame_%04d.png"),
        "-vf", f"setpts={1/intensity}*PTS", "-af", f"atempo={intensity}",
        "-y", output_file
    ]
    subprocess.run(cmd, check=True)

# Example usage
filters = [
    {"location": 0, "duration": 60, "intensity": 2.0},
    {"location": 120, "duration": 30, "intensity": 0.5}
]

split_and_process_video("raining.mp4", "s-raining.mp4", filters)
