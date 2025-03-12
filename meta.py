from lib import get_video_metadata, get_video_duration, estimate_crf
from sys import argv

file = argv[1]
print(get_video_duration(file), get_video_metadata(file))


def main():
    codec = 'h264'
    bitrate = 2000000  # 2 Mbps
    resolution = (3840, 2160)  # 4K resolution
    fps = 30.0  # 30 frames per second

    crf = estimate_crf(codec, bitrate, resolution, fps)
    print(f"Estimated CRF for 4K video at 2Mbps: {crf}")

if __name__ == "__main__":
    main()