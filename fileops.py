import os
def write_file_list(file_list_path, segment_filenames, temp_directory):
    """Write a list of segment filenames to a file for FFmpeg concatenation."""
    with open(file_list_path, "w") as f:
        for filename in segment_filenames:
            relative_filename = os.path.relpath(filename, temp_directory)
            f.write(f"file '{relative_filename}'\n")