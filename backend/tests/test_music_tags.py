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

    @pytest.mark.parametrize('raw', [
        '99999999999',   # larger than INT
        '2147483648',    # one past INT max
        '10000',         # past our own ceiling
        '0',             # track numbering is 1-based
        '-5',            # negative
    ])
    def test_rejects_values_unfit_for_the_column(self, raw):
        """An out-of-range insert would abort the whole scan, not one file."""
        assert track_number(raw) is None

    def test_accepts_the_bottom_of_the_range(self):
        assert track_number('1') == 1

    def test_accepts_the_top_of_the_range(self):
        assert track_number('9999') == 9999


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


def test_the_filename_fallback_honours_the_text_limit(tmp_path):
    """The fallback title is clamped like a tag value is.

    No filesystem permits a basename this long (NAME_MAX is 255 bytes), so the
    clamp cannot fire on real input today. It is here to keep the fallback
    consistent with MAX_TEXT_LENGTH should that drop below 255 because the
    column narrowed — which test_track_text_columns_match_the_tag_truncation
    would then require. The path is deliberately not written to disk.
    """
    path = tmp_path / ('n' * 400 + '.mp3')

    assert len(read_tags(str(path))['title']) == 255


def test_valid_file_with_no_tag_block(tmp_path):
    """Distinct from an unparseable file: mutagen succeeds, .tags is None.

    Built with the stdlib so the test needs no encoder.
    """
    import wave

    path = tmp_path / 'Untagged Song.wav'
    with wave.open(str(path), 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b'\x00\x00' * 8000)

    tags = read_tags(str(path))

    assert tags['title'] == 'Untagged Song'
    assert tags['artist'] is None
    assert tags['album'] is None
    assert tags['track_no'] is None
    assert tags['duration_seconds'] == 1


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

    def test_implausible_duration_is_dropped(self, tagged, tmp_path):
        """A corrupt header must not put an out-of-range value in an INT."""
        tagged({'title': ['x']}, length=1e12)

        assert read_tags(str(tmp_path / 'x.mp3'))['duration_seconds'] is None

    def test_over_length_tags_are_truncated(self, tagged, tmp_path):
        """VARCHAR(255) columns; a longer value fails the insert outright."""
        tagged({
            'title': ['T' * 500],
            'artist': ['A' * 500],
            'album': ['B' * 500],
        })

        tags = read_tags(str(tmp_path / 'x.mp3'))

        assert len(tags['title']) == 255
        assert len(tags['artist']) == 255
        assert len(tags['album']) == 255
        assert tags['title'] == 'T' * 255

    def test_a_tag_at_the_limit_is_untouched(self, tagged, tmp_path):
        tagged({'title': ['T' * 255]})

        assert read_tags(str(tmp_path / 'x.mp3'))['title'] == 'T' * 255


def test_reads_id3_tags_from_a_wav_file(tmp_path):
    """mutagen has no easy-mode WAV class, so raw ID3 frames must be read.

    Without this, every tagged .wav is indexed under its filename with no
    artist or album, and searching for the artist finds nothing.
    """
    import wave

    from mutagen.id3 import TALB, TIT2, TPE1, TRCK
    from mutagen.wave import WAVE

    path = tmp_path / '03 whatever.wav'
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b'\0\0' * 8000)
    audio = WAVE(str(path))
    audio.add_tags()
    audio['TIT2'] = TIT2(encoding=3, text='Song')
    audio['TPE1'] = TPE1(encoding=3, text='Band')
    audio['TALB'] = TALB(encoding=3, text='Record')
    audio['TRCK'] = TRCK(encoding=3, text='3/10')
    audio.save()

    tags = read_tags(str(path))

    assert tags == {'title': 'Song', 'artist': 'Band', 'album': 'Record',
                    'track_no': 3, 'duration_seconds': 1}


class TestFilenameFallback:
    def test_an_untagged_artist_dash_title_name_is_split(self, tmp_path):
        path = tmp_path / 'Ariana Grande - petal.mp3'
        path.write_bytes(b'not really an mp3')

        tags = read_tags(str(path))

        assert (tags['artist'], tags['title']) == ('Ariana Grande', 'petal')

    def test_only_the_first_dash_splits(self, tmp_path):
        path = tmp_path / 'Taylor Swift - I Knew It - live.mp3'
        path.write_bytes(b'x')

        tags = read_tags(str(path))

        assert (tags['artist'], tags['title']) == ('Taylor Swift', 'I Knew It - live')

    def test_a_double_dash_separates_too(self, tmp_path):
        path = tmp_path / 'Donna Summer -- Hot Stuff.mp3'
        path.write_bytes(b'x')

        tags = read_tags(str(path))

        assert (tags['artist'], tags['title']) == ('Donna Summer', 'Hot Stuff')

    def test_a_hyphenated_word_is_not_a_separator(self, tmp_path):
        path = tmp_path / 'Self-Titled Song.mp3'
        path.write_bytes(b'x')

        assert read_tags(str(path))['artist'] is None

    def test_a_name_without_the_pattern_stays_the_title(self, tmp_path):
        path = tmp_path / 'Some Song.mp3'
        path.write_bytes(b'x')

        tags = read_tags(str(path))

        assert (tags['artist'], tags['title']) == (None, 'Some Song')

    def test_a_dash_with_nothing_either_side_is_not_split(self, tmp_path):
        path = tmp_path / ' - .mp3'
        path.write_bytes(b'x')

        assert read_tags(str(path))['artist'] is None

    def test_real_tags_are_never_overridden_by_the_name(self, tagged, tmp_path):
        """A tagged file named "Wrong - Wrong.mp3" keeps its tags."""
        tagged({'title': ['Right Title'], 'artist': ['Right Artist']})
        path = tmp_path / 'Wrong - Wrong.mp3'
        path.write_bytes(b'x')

        tags = read_tags(str(path))

        assert (tags['artist'], tags['title']) == ('Right Artist', 'Right Title')
