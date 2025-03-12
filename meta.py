from lib import get_video_metadata, get_video_duration, estimate_crf
from sys import argv


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
  #main()