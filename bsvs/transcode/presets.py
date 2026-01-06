"""Transcoding quality presets."""

from dataclasses import dataclass


@dataclass
class QualityPreset:
    """Video quality preset configuration."""
    name: str
    height: int
    bitrate_kbps: int
    audio_bitrate_kbps: int = 128


# Standard quality presets
QUALITY_PRESETS = {
    "1080p": QualityPreset(name="1080p", height=1080, bitrate_kbps=5000),
    "720p": QualityPreset(name="720p", height=720, bitrate_kbps=2500),
    "480p": QualityPreset(name="480p", height=480, bitrate_kbps=1000),
    "360p": QualityPreset(name="360p", height=360, bitrate_kbps=600),
}


def get_preset(name: str) -> QualityPreset:
    """Get a quality preset by name."""
    if name not in QUALITY_PRESETS:
        raise ValueError(f"Unknown preset: {name}. Available: {list(QUALITY_PRESETS.keys())}")
    return QUALITY_PRESETS[name]


def get_applicable_presets(source_height: int, requested: list[str]) -> list[QualityPreset]:
    """
    Get presets that are applicable for the source video.

    Only returns presets where the target height is <= source height.
    """
    applicable = []
    for name in requested:
        preset = get_preset(name)
        if preset.height <= source_height:
            applicable.append(preset)

    # If no presets are applicable (source is very low res), use lowest requested
    if not applicable and requested:
        lowest = min(requested, key=lambda n: QUALITY_PRESETS[n].height)
        applicable.append(get_preset(lowest))

    return applicable
