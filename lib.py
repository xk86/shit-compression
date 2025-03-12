import math

def estimate_crf(codec, bitrate, resolution, fps):
    """
    Estimate CRF dynamically based on the pixels-frame-to-bitrate ratio.
    codec: str (e.g., 'h264', 'hevc', 'vp9', 'av1')
    bitrate: int (in bits per second)
    resolution: tuple (width, height)
    fps: float (frames per second)
    """

    # Define CRF range per codec (min_crf = highest quality, max_crf = lowest quality)
    codec_crf_range = {
        'h264': (0, 51),
        'hevc': (0, 51),
        'vp9': (0, 63),
        'av1': (0, 63),
        'aac': (1, 5),    # For audio codecs, quality presets
        'opus': (64, 128) # kbps target for audio codecs
    }

    if codec not in codec_crf_range:
        raise ValueError(f"Unsupported codec '{codec}'")

    width, height = resolution
    pixels = width * height

    # Compute quality score
    quality_score = (pixels * fps) / bitrate  # pixels-frames per bit

    # Apply logarithmic scaling to distribute values evenly
    scaled_score = math.log1p(quality_score)

    # Normalize scaled score between 0 and 1 based on practical observed ranges
    # Assumption: scaled_score typically varies between 0.5 (excellent) and ~5.0 (poor)
    min_log, max_log = 0.5, 5.0
    normalized_score = (scaled_score - min_log) / (max_log - min_log)
    normalized_score = min(max(normalized_score, 0), 1)  # Clamp 0-1

    # Map normalized score inversely to CRF range (higher quality = lower CRF)
    min_crf, max_crf = codec_crf_range[codec]
    estimated_crf = min_crf + (normalized_score * (max_crf - min_crf))

    return int(round(estimated_crf))

def compute_quality_score(bitrate, resolution, fps):
    width, height = resolution
    pixels = width * height
    return (pixels * fps) / bitrate  # Higher means lower quality (fewer bits per pixel-frame)

def map_quality_to_crf(codec, quality_score):
    codec_crf_ranges = {
        'h264': (0, 51),
        'hevc': (0, 51),
        'vp9': (0, 63),
        'av1': (0, 63),
        'aac': (1, 5),
        'opus': (64, 128),
    }

    min_crf, max_crf = codec_crf_ranges.get(codec, (0, 51))

    # Logarithmic scale ensures smoothness over a large range
    scaled_score = math.log1p(quality_score)

    # Map score inversely across full CRF range
    # Higher quality_score → higher CRF (lower quality)
    normalized_score = scaled_score / (scaled_score + 1)  # smooth 0-1 mapping

    estimated_crf = min_crf + normalized_score * (max_crf - min_crf)

    return int(round(min(max_crf, max(min_crf, estimated_crf))))

#def estimate_crf(codec, bitrate, resolution, fps):
#    """
#    Estimates CRF for a given codec based on bitrate, resolution, and fps.
#    
#    Parameters:
#        codec (str): Codec name ('h264', 'hevc', 'vp9', 'av1', etc.).
#        bitrate (int): Bitrate in bits per second.
#        resolution (tuple): Resolution as (width, height).
#        fps (float): Frames per second.
#        
#    Returns:
#        int: Estimated CRF value appropriate for the codec.
#    """
#    quality_score = compute_quality_score(bitrate, resolution, fps)
#    return map_quality_to_crf(codec, quality_score)