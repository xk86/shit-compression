import subprocess
import os
from lib import estimate_crf

# Function to split and process the video based on specified speed adjustments
def split_and_process_video(input_file, output_file, filters):
    temp_dir = os.path.join(os.getcwd(), 'temp_processing')
    os.makedirs(temp_dir, exist_ok=True)
    segments = []
    concat_list_path = os.path.join(temp_dir, "concat_list.txt")

    duration = get_video_duration(input_file)
    metadata = get_video_metadata(input_file)
    last_split = 0
    part_index = 0

    with open(concat_list_path, "w") as concat_list:
        for f in sorted(filters, key=lambda x: x['location']):
            location, duration_segment, intensity = f["location"], f["duration"], f["intensity"]

            if location > last_split:
                normal_segment = os.path.join(temp_dir, f"part_{part_index}.mp4")
                extract_segment(input_file, last_split, location, normal_segment)
                concat_list.write(f"file '{normal_segment}'\n")
                segments.append(normal_segment)
                part_index += 1

            modified_segment = os.path.join(temp_dir, f"part_{part_index}.mp4")
            process_segment(input_file, location, location + duration_segment, modified_segment, intensity, metadata)
            concat_list.write(f"file '{modified_segment}'\n")
            segments.append(modified_segment)
            part_index += 1
            last_split = location + duration_segment

        if last_split < duration:
            remaining_segment = os.path.join(temp_dir, f"part_{part_index}.mp4")
            extract_segment(input_file, last_split, duration, remaining_segment)
            concat_list.write(f"file '{remaining_segment}'\n")
            segments.append(remaining_segment)

    concatenate_segments(concat_list_path, output_file, metadata)

def get_video_duration(input_file):
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", input_file], stdout=subprocess.PIPE, text=True, check=True)
    return float(result.stdout.strip())

def get_video_metadata(input_file):
    video_cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name,width,height,r_frame_rate,bit_rate", "-of", "csv=p=0", input_file]
    audio_cmd = ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_name,bit_rate", "-of", "csv=p=0", input_file]

    video_output = subprocess.run(video_cmd, stdout=subprocess.PIPE, text=True, check=True).stdout.strip()
    audio_output = subprocess.run(audio_cmd, stdout=subprocess.PIPE, text=True, check=True).stdout.strip()

    video_result = video_output.split(',') if video_output else []
    audio_result = audio_output.split(',') if audio_output else []

    vcodec = video_result[0] if len(video_result) > 0 else "h264"
    width = int(video_result[1]) if len(video_result) > 1 and video_result[1].isdigit() else 1920
    height = int(video_result[2]) if len(video_result) > 2 and video_result[2].isdigit() else 1080
    fps_str = video_result[3] if len(video_result) > 3 else "30/1"
    vbitrate = int(video_result[4]) if len(video_result) > 4 and video_result[4].isdigit() else 2000000

    num, den = map(int, fps_str.split('/')) if '/' in fps_str else (30, 1)
    fps = num / den

    acodec = audio_result[0] if len(audio_result) > 0 else "aac"
    abitrate = int(audio_result[1]) if len(audio_result) > 1 and audio_result[1].isdigit() else 128000

    vcrf = estimate_crf(vcodec, vbitrate, (width, height), fps)
    acrf = estimate_crf(acodec, abitrate, (1, 1), 1)

    return {"fps": fps, "vcodec": vcodec, "acodec": acodec, "vcrf": vcrf, "acrf": acrf, "vbitrate": vbitrate, "abitrate": abitrate, "resolution": (width, height)}

def extract_segment(input_file, start, end, output_file):
    subprocess.run(["ffmpeg", "-i", input_file, "-ss", str(start), "-to", str(end), "-c", "copy", "-y", output_file], check=True)

def process_segment(input_file, start, end, output_file, intensity, metadata):
    adjusted_bitrate = int(metadata["vbitrate"] / intensity)
    adjusted_crf = estimate_crf(metadata["vcodec"], adjusted_bitrate, metadata["resolution"], metadata["fps"])

    subprocess.run([
        "ffmpeg", "-i", input_file, "-ss", str(start), "-to", str(end),
        "-vf", f"setpts={1/intensity}*PTS,fps={metadata['fps']}",
        "-af", f"atempo={intensity}",
        "-c:v", metadata["vcodec"], "-crf", str(adjusted_crf), "-b:v", str(adjusted_bitrate),
        "-c:a", metadata["acodec"], "-b:a", str(metadata["abitrate"]),
        "-y", output_file
    ], check=True)

def concatenate_segments(concat_list_path, output_file, metadata):
    subprocess.run(["ffmpeg", "-f", "concat", "-safe", "0", "-i", concat_list_path, "-c", "copy", "-y", output_file], check=True)

filters = [
    {"location": 0, "duration": 30, "intensity": 2.0},
    {"location": 45, "duration": 15, "intensity": 3.0}
]

split_and_process_video("raining.mp4", "s-raining.mp4", filters)
#print(get_video_metadata("raining.mp4"), "\n",get_video_metadata("s-raining.mp4"))

#print(get_video_metadata("raining.mp4"))
