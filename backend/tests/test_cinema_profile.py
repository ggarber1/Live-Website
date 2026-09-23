import pytest

from cinema.profile import DEVICE_PROFILE, H264_MAX_LEVEL, H264_PROFILES, MAX_AUDIO_CHANNELS, playback_kind


def source(container, vcodec, acodec, profile=None):
    video = {'Type': 'Video', 'Codec': vcodec}
    if profile:
        video['Profile'] = profile
    return {'Container': container, 'MediaStreams': [video, {'Type': 'Audio', 'Codec': acodec}]}


@pytest.mark.parametrize('media, expected', [
    (source('mp4', 'h264', 'aac'), 'direct'),
    (source('mp4', 'h264', 'mp3'), 'direct'),
    (source('webm', 'vp9', 'opus'), 'direct'),
    (source('mkv', 'h264', 'ac3'), 'remux'),
    (source('mkv', 'h264', 'aac'), 'remux'),          # container alone forces a remux
    (source('mkv', 'h264', 'ac3', 'High'), 'remux'),
    (source('mkv', 'h264', 'ac3', 'High 10'), 'transcode'),  # 10-bit h264: not copyable
    (source('mkv', 'hevc', 'ac3'), 'transcode'),
    (source('mp4', 'hevc', 'aac'), 'transcode'),
    (source('avi', 'mpeg4', 'mp3'), 'transcode'),
])
def test_playback_kind(media, expected):
    assert playback_kind(media) == expected


def test_no_video_stream_is_unknown():
    assert playback_kind({'Container': 'mkv', 'MediaStreams': []}) == 'unknown'


def test_a_silent_film_can_still_be_direct():
    media = {'Container': 'mp4', 'MediaStreams': [{'Type': 'Video', 'Codec': 'h264'}]}

    assert playback_kind(media) == 'remux'  # no audio pair to match; remuxing is harmless


class TestProfileGuards:
    """Dropping these silently costs a full video transcode on the Pi."""

    def h264_conditions(self):
        for codec in DEVICE_PROFILE['CodecProfiles']:
            if codec['Type'] == 'Video' and codec['Codec'] == 'h264':
                return {c['Property']: c['Value'] for c in codec['Conditions']}
        raise AssertionError('no h264 codec profile')

    def test_lists_every_copyable_h264_profile(self):
        assert self.h264_conditions()['VideoProfile'] == H264_PROFILES
        for name in ('high', 'main', 'baseline', 'constrained baseline'):
            assert name in H264_PROFILES.split('|')

    def test_allows_level_51(self):
        assert self.h264_conditions()['VideoLevel'] == H264_MAX_LEVEL == '51'

    def test_surround_aac_direct_plays(self):
        """A 5.1 AAC mp4 was being remuxed just to downmix; browsers do that."""
        [aac] = [c for c in DEVICE_PROFILE['CodecProfiles'] if c['Type'] == 'VideoAudio']
        channels = next(c['Value'] for c in aac['Conditions'] if c['Property'] == 'AudioChannels')
        assert int(channels) >= 6
        assert MAX_AUDIO_CHANNELS == 6

    def test_transcodes_to_hls_h264_aac(self):
        [hls] = DEVICE_PROFILE['TranscodingProfiles']
        assert (hls['Protocol'], hls['VideoCodec'], hls['AudioCodec']) == ('hls', 'h264', 'aac')
