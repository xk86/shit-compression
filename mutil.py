from avmeta import *
from meta import *
from sys import argv
# Helper script for testing internal library functions

hq_4k = {
  "codec": "h264",
  "bitrate": 200000000, # 200 Mbps
  "resolution": (3840, 2160),
  "fps": 24.
}

mq_4k = {
  "codec": "h264",
  "bitrate": 2000000, # 2 Mbps
  "resolution": (3840, 2160),
  "fps": 24.
}

lq_4k = {
  "codec": "h264",
  "bitrate": 200000, # 200 Kbps
  "resolution": (3840, 2160),
  "fps": 24.
}

samples = [hq_4k, mq_4k, lq_4k]

def main():
  for sample in samples:
    crf = estimate_crf(sample["codec"], sample["bitrate"], sample["resolution"], sample["fps"])
    print(f"Estimated CRF for 4K video at {sample['bitrate'] / 1000000} Mbps: {crf}")

file = argv[1]
duration = get_video_duration(file)
 # print(get_video_duration(file), get_video_metadata(file))
 # print(file," video bitrate ", get_bit_rate(file) / 1000, "kbps",)
 # print(file, " video avg bits per frame", get_bit_frame_rate(file) / 1000, "kbps/f")
 # print(file, "audio bitrate ", get_bit_rate(file, type="audio") / 1000, "kbps")

if file == "testing_file.mkv" or file == "compressed_out_test.mkv":
  with open("testing_file.mshit", "r") as f:
    metadata = eval(f.read())
  scenes = metadata["segments"]
  passthru = add_pass_through_segments(scenes, duration)
  mutated = get_mutated_segments(duration, passthru)
  mut_keyfs = adjust_segments_to_keyframes(file, mutated, os.path.join("temp_out_test"))


  inverted_scenes = [({'start': x['start'], 'end': x['end'],'interest': 1/x['interest']}) for x in mut_keyfs]

  print("Original: ", scenes, "\n",
        "\nAdding passthrough ", passthru, "\n",
        "\nMutating for decoding ", mutated, "\n",
        "\nAdjusting to keyframes ", mut_keyfs, "\n")
  print("Inverting the intensities ", inverted_scenes)

if file == "temp_out_test/decode_pre_2.mkv":
  get_bit_rate(file, "video")