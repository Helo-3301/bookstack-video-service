"""FFmpeg wrapper for video transcoding."""

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

from bsvs.transcode.presets import QualityPreset

logger = logging.getLogger(__name__)


@dataclass
class VideoInfo:
    """Video metadata from ffprobe."""
    width: int
    height: int
    duration_seconds: float
    codec: str
    fps: float


def probe_video(input_path: str | Path) -> VideoInfo:
    """
    Probe video file to get metadata using ffprobe.

    Args:
        input_path: Path to the video file

    Returns:
        VideoInfo with video metadata
    """
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(input_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")

    data = json.loads(result.stdout)

    # Find video stream
    video_stream = None
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            video_stream = stream
            break

    if not video_stream:
        raise ValueError("No video stream found in file")

    # Parse frame rate (can be "30/1" or "29.97")
    fps_str = video_stream.get("r_frame_rate", "30/1")
    if "/" in fps_str:
        num, den = fps_str.split("/")
        fps = float(num) / float(den)
    else:
        fps = float(fps_str)

    # Get duration from format or stream
    duration = float(data.get("format", {}).get("duration", 0))
    if duration == 0:
        duration = float(video_stream.get("duration", 0))

    return VideoInfo(
        width=int(video_stream.get("width", 0)),
        height=int(video_stream.get("height", 0)),
        duration_seconds=duration,
        codec=video_stream.get("codec_name", "unknown"),
        fps=fps,
    )


def transcode_to_hls(
    input_path: str | Path,
    output_dir: str | Path,
    preset: QualityPreset,
    segment_duration: int = 6,
) -> Path:
    """
    Transcode video to HLS format at the specified quality.

    Args:
        input_path: Path to source video
        output_dir: Directory to write HLS files (will create subdirectory for quality)
        preset: Quality preset to use
        segment_duration: HLS segment duration in seconds

    Returns:
        Path to the playlist file
    """
    input_path = Path(input_path)
    output_dir = Path(output_dir) / preset.name
    output_dir.mkdir(parents=True, exist_ok=True)

    playlist_path = output_dir / "playlist.m3u8"
    segment_pattern = output_dir / "segment_%03d.ts"

    # Calculate width maintaining aspect ratio (must be divisible by 2)
    # We'll let FFmpeg handle this with scale filter

    cmd = [
        "ffmpeg",
        "-i", str(input_path),
        "-y",  # Overwrite output
        # Video encoding
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "23",
        "-profile:v", "main",
        "-level", "4.0",
        # Scale to target height, maintain aspect ratio, ensure even dimensions
        "-vf", f"scale=-2:{preset.height}",
        # Target bitrate
        "-b:v", f"{preset.bitrate_kbps}k",
        "-maxrate", f"{int(preset.bitrate_kbps * 1.5)}k",
        "-bufsize", f"{preset.bitrate_kbps * 2}k",
        # Audio encoding
        "-c:a", "aac",
        "-b:a", f"{preset.audio_bitrate_kbps}k",
        "-ar", "44100",
        # HLS output
        "-f", "hls",
        "-hls_time", str(segment_duration),
        "-hls_list_size", "0",  # Keep all segments in playlist
        "-hls_segment_filename", str(segment_pattern),
        "-hls_playlist_type", "vod",
        str(playlist_path),
    ]

    logger.info(f"Transcoding to {preset.name}: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"FFmpeg failed: {result.stderr}")
        raise RuntimeError(f"Transcoding failed: {result.stderr[:500]}")

    logger.info(f"Transcoding complete: {playlist_path}")
    return playlist_path


def extract_thumbnails(
    input_path: str | Path,
    output_dir: str | Path,
    count: int = 4,
) -> list[Path]:
    """
    Extract thumbnail images from video at various timestamps.

    Args:
        input_path: Path to source video
        output_dir: Directory to write thumbnails
        count: Number of thumbnails to extract

    Returns:
        List of paths to generated thumbnails
    """
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Get video duration
    info = probe_video(input_path)

    thumbnails = []
    percentages = [0, 25, 50, 75][:count]

    for pct in percentages:
        timestamp = (info.duration_seconds * pct) / 100
        output_path = output_dir / f"thumb_{pct}.jpg"

        cmd = [
            "ffmpeg",
            "-ss", str(timestamp),
            "-i", str(input_path),
            "-y",
            "-vframes", "1",
            "-vf", "scale=640:-2",
            "-q:v", "2",
            str(output_path),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            thumbnails.append(output_path)
            logger.info(f"Generated thumbnail: {output_path}")
        else:
            logger.warning(f"Failed to generate thumbnail at {pct}%: {result.stderr}")

    return thumbnails
