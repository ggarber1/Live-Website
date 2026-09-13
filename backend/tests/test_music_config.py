import os

import pytest

from music.config import music_dir, resolve_inside_music_dir


class TestMusicDir:
    def test_reads_the_environment_variable(self, monkeypatch, tmp_path):
        monkeypatch.setenv('MUSIC_DIR', str(tmp_path))

        assert music_dir() == os.path.realpath(str(tmp_path))

    def test_missing_variable_names_it(self, monkeypatch):
        monkeypatch.delenv('MUSIC_DIR', raising=False)

        with pytest.raises(RuntimeError) as err:
            music_dir()

        assert 'MUSIC_DIR' in str(err.value)

    def test_blank_variable_is_treated_as_missing(self, monkeypatch):
        monkeypatch.setenv('MUSIC_DIR', '')

        with pytest.raises(RuntimeError):
            music_dir()

    def test_result_is_absolute(self, monkeypatch, tmp_path):
        monkeypatch.setenv('MUSIC_DIR', str(tmp_path))

        assert os.path.isabs(music_dir())

    def test_relative_path_is_rejected(self, monkeypatch):
        """A relative value would resolve against an unpredictable cwd."""
        monkeypatch.setenv('MUSIC_DIR', 'media/music')

        with pytest.raises(RuntimeError) as err:
            music_dir()

        assert 'absolute' in str(err.value)


class TestResolveInsideMusicDir:
    def test_accepts_a_file_inside_the_root(self, monkeypatch, tmp_path):
        monkeypatch.setenv('MUSIC_DIR', str(tmp_path))
        target = tmp_path / 'album' / 'song.mp3'
        target.parent.mkdir()
        target.write_bytes(b'x')

        assert resolve_inside_music_dir(str(target)) == os.path.realpath(str(target))

    def test_rejects_a_path_outside_the_root(self, monkeypatch, tmp_path):
        monkeypatch.setenv('MUSIC_DIR', str(tmp_path / 'music'))
        (tmp_path / 'music').mkdir()
        outside = tmp_path / 'secret.txt'
        outside.write_bytes(b'x')

        assert resolve_inside_music_dir(str(outside)) is None

    def test_rejects_traversal(self, monkeypatch, tmp_path):
        monkeypatch.setenv('MUSIC_DIR', str(tmp_path / 'music'))
        (tmp_path / 'music').mkdir()

        assert resolve_inside_music_dir(str(tmp_path / 'music' / '..' / 'etc')) is None

    def test_rejects_a_symlink_escaping_the_root(self, monkeypatch, tmp_path):
        """The scanner indexes whatever is on disk, including planted symlinks."""
        root = tmp_path / 'music'
        root.mkdir()
        secret = tmp_path / 'secret.txt'
        secret.write_bytes(b'x')
        link = root / 'innocent.mp3'
        link.symlink_to(secret)
        monkeypatch.setenv('MUSIC_DIR', str(root))

        assert resolve_inside_music_dir(str(link)) is None

    def test_rejects_a_sibling_directory_with_the_same_prefix(self, monkeypatch, tmp_path):
        """/music must not be treated as containing /music-backup."""
        (tmp_path / 'music').mkdir()
        sibling = tmp_path / 'music-backup'
        sibling.mkdir()
        (sibling / 'song.mp3').write_bytes(b'x')
        monkeypatch.setenv('MUSIC_DIR', str(tmp_path / 'music'))

        assert resolve_inside_music_dir(str(sibling / 'song.mp3')) is None

    def test_rejects_an_empty_path(self, monkeypatch, tmp_path):
        """realpath('') is the cwd, which must not be treated as contained."""
        monkeypatch.setenv('MUSIC_DIR', str(tmp_path))

        assert resolve_inside_music_dir('') is None

    def test_rejects_an_empty_path_before_consulting_music_dir(self, monkeypatch):
        """Pins the guard's placement: it returns before music_dir() can raise.

        Without this, a refactor could move the falsy check below the config
        lookup and turn an internal bug into a RuntimeError, with no test
        noticing.
        """
        monkeypatch.delenv('MUSIC_DIR', raising=False)

        assert resolve_inside_music_dir('') is None

    def test_accepts_the_root_itself(self, monkeypatch, tmp_path):
        monkeypatch.setenv('MUSIC_DIR', str(tmp_path))

        assert resolve_inside_music_dir(str(tmp_path)) == os.path.realpath(str(tmp_path))
