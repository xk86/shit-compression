from avmeta import *
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

if __name__ == "__main__":
  file = argv[1]
  print(get_video_duration(file), get_video_metadata(file))
  print(file," video bitrate ", get_bit_rate(file) / 1000, "kbps",)
  print(file, " video avg bits per frame", get_bit_frame_rate(file) / 1000, "kbps/f")
  print(file, "audio bitrate ", get_bit_rate(file, type="audio") / 1000, "kbps")
  #main()