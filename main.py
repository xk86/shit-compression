import subprocess
import os

# Function to split and process the video based on specified speed adjustments
def split_and_process_video(input_file, output_file, filters):
    temp_dir = os.path.join(os.getcwd(), 'temp_processing')  # Set up temp working directory
    os.makedirs(temp_dir, exist_ok=True)  # Ensure the directory exists
    segments = []
    concat_list_path = os.path.join(temp_dir, "concat_list.txt")  # File to store concatenation list
    
    duration = get_video_duration(input_file)  # Get total video duration
    last_split = 0
    part_index = 0 
    
    with open(concat_list_path, "w") as concat_list:
        for f in sorted(filters, key=lambda x: x['location']):
            location, duration_segment, intensity = f["location"], f["duration"], f["intensity"]
            
            # Extract and keep unmodified segments
            if location > last_split:
                normal_segment = os.path.join(temp_dir, f"part_{part_index}.mp4")
                extract_segment(input_file, last_split, location, normal_segment)
                concat_list.write(f"file '{normal_segment}'\n")
                segments.append(normal_segment)
                part_index += 1
            
            # Process and speed up the specified segment
            modified_segment = os.path.join(temp_dir, f"part_{part_index}.mp4")
            process_segment(input_file, location, location + duration_segment, modified_segment, intensity)
            concat_list.write(f"file '{modified_segment}'\n")
            segments.append(modified_segment)
            part_index += 1
            last_split = location + duration_segment
        
        # Extract and keep any remaining segment after the last modified one
        if last_split < duration:
            remaining_segment = os.path.join(temp_dir, f"part_{part_index}.mp4")
            extract_segment(input_file, last_split, duration, remaining_segment)
            concat_list.write(f"file '{remaining_segment}'\n")
            segments.append(remaining_segment)
    
    # Concatenate all segments into the final output file
    concatenate_segments(concat_list_path, output_file)

# Function to get the total duration of the input video
def get_video_duration(input_file):
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", input_file], stdout=subprocess.PIPE, text=True, check=True)
    return float(result.stdout.strip())

# Function to extract a segment of the video without re-encoding
def extract_segment(input_file, start, end, output_file):
    subprocess.run(["ffmpeg", "-i", input_file, "-ss", str(start), "-to", str(end), "-c", "copy", "-y", output_file], check=True)

# Function to process a segment by adjusting its speed
def process_segment(input_file, start, end, output_file, intensity):
    subprocess.run(["ffmpeg", "-i", input_file, "-ss", str(start), "-to", str(end), "-vf", f"setpts={1/intensity}*PTS", "-af", f"atempo={intensity}", "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-c:a", "aac", "-b:a", "192k", "-y", output_file], check=True)

# Function to concatenate all processed segments into a final output video
def concatenate_segments(concat_list_path, output_file):
    subprocess.run(["ffmpeg", "-f", "concat", "-safe", "0", "-i", concat_list_path, "-c", "copy", "-y", output_file], check=True)

# Example usage - defining the speed adjustments
filters = [
    {"location": 0, "duration": 60, "intensity": 2.0},
    {"location": 120, "duration": 30, "intensity": 1.5}
]

# Run the script on "raining.mp4" and output "s-raining.mp4"
split_and_process_video("raining.mp4", "s-raining.mp4", filters)
