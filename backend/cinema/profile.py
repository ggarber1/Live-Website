"""The device profile we send Jellyfin, and what its answer costs.

This is a correctness matter, not a preference: without the h264 profile
conditions Jellyfin re-encodes copyable High-profile video down to
constrained baseline, which on the Pi is the difference between a film
that plays and one that stutters. Measured on 12.1.0; see the spec.
"""

H264_PROFILES = 'high|main|baseline|constrained baseline'
H264_MAX_LEVEL = '51'
MAX_AUDIO_CHANNELS = 6

DEVICE_PROFILE = {
    'Name': 'livs-browser',
    'MaxStreamingBitrate': 20_000_000,
    'DirectPlayProfiles': [
        {'Container': 'mp4,m4v', 'Type': 'Video', 'VideoCodec': 'h264', 'AudioCodec': 'aac,mp3'},
        {'Container': 'webm', 'Type': 'Video', 'VideoCodec': 'vp9,av1', 'AudioCodec': 'opus,vorbis'},
    ],
    'TranscodingProfiles': [
        {'Container': 'ts', 'Type': 'Video', 'VideoCodec': 'h264', 'AudioCodec': 'aac',
         'Protocol': 'hls', 'Context': 'Streaming', 'MaxAudioChannels': '2',
         'MinSegments': 1, 'BreakOnNonKeyFrames': True},
    ],
    'CodecProfiles': [
        {'Type': 'Video', 'Codec': 'h264', 'Conditions': [
            {'Condition': 'EqualsAny', 'Property': 'VideoProfile', 'Value': H264_PROFILES, 'IsRequired': False},
            {'Condition': 'LessThanEqual', 'Property': 'VideoLevel', 'Value': H264_MAX_LEVEL, 'IsRequired': False},
            {'Condition': 'NotEquals', 'Property': 'IsAnamorphic', 'Value': 'true', 'IsRequired': False},
            {'Condition': 'EqualsAny', 'Property': 'VideoRangeType', 'Value': 'SDR', 'IsRequired': False},
        ]},
        # Browsers decode 5.1 AAC and downmix it themselves. Capping this at
        # stereo made Jellyfin remux every surround film for no gain.
        {'Type': 'VideoAudio', 'Codec': 'aac', 'Conditions': [
            {'Condition': 'LessThanEqual', 'Property': 'AudioChannels', 'Value': str(MAX_AUDIO_CHANNELS), 'IsRequired': False},
        ]},
    ],
    'SubtitleProfiles': [
        {'Format': 'vtt', 'Method': 'External'},
        {'Format': 'subrip', 'Method': 'External'},
    ],
}

DIRECT_CONTAINERS = {'mp4', 'm4v', 'webm'}
DIRECT_PAIRS = {
    ('h264', 'aac'), ('h264', 'mp3'),
    ('vp9', 'opus'), ('vp9', 'vorbis'), ('av1', 'opus'), ('av1', 'vorbis'),
}
COPYABLE_VIDEO = {'h264'}
COPYABLE_H264_PROFILES = {p.strip() for p in H264_PROFILES.split('|')}


def _streams(media_source):
    video = audio = None
    for stream in media_source.get('MediaStreams', []):
        if stream.get('Type') == 'Video' and video is None:
            video = stream
        elif stream.get('Type') == 'Audio' and audio is None:
            audio = stream
    return video, audio


def playback_kind(media_source):
    """direct, remux or transcode: what a browser would need for this file.

    Shown in the UI before Play so the expensive case is not a surprise.
    Mirrors the profile above; it does not consult Jellyfin.
    """
    video, audio = _streams(media_source)
    if video is None:
        return 'unknown'
    container = (media_source.get('Container') or '').lower()
    vcodec = (video.get('Codec') or '').lower()
    acodec = (audio.get('Codec') or '').lower() if audio else ''
    if container in DIRECT_CONTAINERS and (vcodec, acodec) in DIRECT_PAIRS:
        return 'direct'
    profile = (video.get('Profile') or '').lower()
    copyable = vcodec in COPYABLE_VIDEO and (not profile or profile in COPYABLE_H264_PROFILES)
    return 'remux' if copyable else 'transcode'
