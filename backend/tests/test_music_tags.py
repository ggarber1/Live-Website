import pytest

from music.tags import AUDIO_EXTENSIONS, read_tags, track_number


class TestTrackNumber:
    @pytest.mark.parametrize('raw,expected', [
        ('3', 3),
        ('03', 3),
        ('3/12', 3),
        (3, 3),
        (None, None),
        ('', None),
        ('A', None),
        ('/12', None),
    ])
    def test_parses_what_it_can(self, raw, expected):
        assert track_number(raw) == expected


class TestReadTags:
    def test_unreadable_file_falls_back_to_the_filename(self, tmp_path):
        path = tmp_path / 'Some Song.mp3'
        path.write_bytes(b'not really an mp3')

        tags = read_tags(str(path))

        assert tags['title'] == 'Some Song'
        assert tags['artist'] is None
        assert tags['album'] is None
        assert tags['track_no'] is None
        assert tags['duration_seconds'] is None

    def test_missing_file_does_not_raise(self, tmp_path):
        tags = read_tags(str(tmp_path / 'nope.mp3'))

        assert tags['title'] == 'nope'

    def test_returns_every_expected_key(self, tmp_path):
        path = tmp_path / 'x.flac'
        path.write_bytes(b'bogus')

        assert set(read_tags(str(path))) == {
            'title', 'artist', 'album', 'track_no', 'duration_seconds',
        }


def test_audio_extensions_are_lowercase_with_dots():
    for ext in AUDIO_EXTENSIONS:
        assert ext.startswith('.')
        assert ext == ext.lower()


class FakeInfo:
    def __init__(self, length):
        self.length = length


class FakeAudio(dict):
    """Stands in for mutagen's easy-mode object: a mapping of key -> list."""

    def __init__(self, tags, length=None):
        super().__init__(tags)
        self.info = FakeInfo(length) if length is not None else None


@pytest.fixture
def tagged(monkeypatch):
    """Make mutagen.File return whatever FakeAudio the test asks for."""
    import music.tags as tags_module

    def install(tags, length=None):
        monkeypatch.setattr(tags_module.mutagen, 'File',
                            lambda path, easy=False: FakeAudio(tags, length))

    return install


class TestReadTagsExtraction:
    def test_reads_title_artist_album_and_track_number(self, tagged, tmp_path):
        tagged({
            'title': ['Space Song'],
            'artist': ['Beach House'],
            'album': ['Depression Cherry'],
            'tracknumber': ['5/10'],
        }, length=301.7)

        tags = read_tags(str(tmp_path / 'irrelevant.mp3'))

        assert tags['title'] == 'Space Song'
        assert tags['artist'] == 'Beach House'
        assert tags['album'] == 'Depression Cherry'
        assert tags['track_no'] == 5

    def test_duration_truncates_to_whole_seconds(self, tagged, tmp_path):
        tagged({'title': ['x']}, length=301.7)

        assert read_tags(str(tmp_path / 'x.mp3'))['duration_seconds'] == 301

    def test_tag_values_are_stripped(self, tagged, tmp_path):
        tagged({'title': ['  Space Song  '], 'artist': ['\tBeach House\n']})

        tags = read_tags(str(tmp_path / 'x.mp3'))

        assert tags['title'] == 'Space Song'
        assert tags['artist'] == 'Beach House'

    def test_blank_title_falls_back_to_the_filename(self, tagged, tmp_path):
        """An empty tag is as good as no tag."""
        tagged({'title': ['   '], 'artist': ['Beach House']})

        tags = read_tags(str(tmp_path / 'On Disk.mp3'))

        assert tags['title'] == 'On Disk'
        assert tags['artist'] == 'Beach House'

    def test_first_non_empty_value_wins_for_multi_valued_tags(self, tagged, tmp_path):
        tagged({'artist': ['', 'Beach House', 'Ignored']})

        assert read_tags(str(tmp_path / 'x.mp3'))['artist'] == 'Beach House'

    def test_missing_info_leaves_duration_null(self, tagged, tmp_path):
        """Some formats give a mapping with no info attribute."""
        tagged({'title': ['x']}, length=None)

        assert read_tags(str(tmp_path / 'x.mp3'))['duration_seconds'] is None
