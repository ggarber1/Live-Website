import os

import pytest

from music.config import music_dir, resolve_inside, resolve_inside_music_dir
from photos.config import photos_dir, resolve_inside_photos_dir, thumbs_dir


class TestPhotosDir:
    def test_reads_the_environment_variable(self, monkeypatch, tmp_path):
        monkeypatch.setenv('PHOTOS_DIR', str(tmp_path))

        assert photos_dir() == os.path.realpath(str(tmp_path))

    @pytest.mark.parametrize('value', [None, ''])
    def test_missing_or_blank_names_the_variable(self, monkeypatch, value):
        if value is None:
            monkeypatch.delenv('PHOTOS_DIR', raising=False)
        else:
            monkeypatch.setenv('PHOTOS_DIR', value)

        with pytest.raises(RuntimeError) as err:
            photos_dir()

        assert 'PHOTOS_DIR' in str(err.value)


class TestThumbsDir:
    def test_defaults_to_a_dot_directory_the_scanner_skips(self, monkeypatch, tmp_path):
        monkeypatch.setenv('PHOTOS_DIR', str(tmp_path))
        monkeypatch.delenv('PHOTOS_THUMBS_DIR', raising=False)

        assert thumbs_dir() == os.path.join(os.path.realpath(str(tmp_path)), '.thumbnails')

    def test_can_be_placed_elsewhere(self, monkeypatch, tmp_path):
        monkeypatch.setenv('PHOTOS_DIR', str(tmp_path / 'photos'))
        monkeypatch.setenv('PHOTOS_THUMBS_DIR', str(tmp_path / 'cache'))

        assert thumbs_dir() == os.path.realpath(str(tmp_path / 'cache'))


# The containment rules are the same for every library root; the music tests
# established them and both roots must keep them.
@pytest.fixture(params=['music', 'photos'])
def library(request, monkeypatch, tmp_path):
    root = tmp_path / request.param
    root.mkdir()
    if request.param == 'music':
        monkeypatch.setenv('MUSIC_DIR', str(root))
        return root, resolve_inside_music_dir, music_dir
    monkeypatch.setenv('PHOTOS_DIR', str(root))
    return root, resolve_inside_photos_dir, photos_dir


class TestResolveInside:
    def test_accepts_a_file_inside_the_root(self, library):
        root, resolve, _ = library
        target = root / 'a' / 'x.jpg'
        target.parent.mkdir()
        target.write_bytes(b'x')

        assert resolve(str(target)) == os.path.realpath(str(target))

    def test_rejects_a_path_outside_the_root(self, library, tmp_path):
        _, resolve, _ = library
        outside = tmp_path / 'secret.txt'
        outside.write_bytes(b'x')

        assert resolve(str(outside)) is None

    def test_rejects_traversal(self, library):
        root, resolve, _ = library

        assert resolve(str(root / '..' / 'etc')) is None

    def test_rejects_a_symlink_escaping_the_root(self, library, tmp_path):
        root, resolve, _ = library
        secret = tmp_path / 'secret.txt'
        secret.write_bytes(b'x')
        link = root / 'innocent.jpg'
        link.symlink_to(secret)

        assert resolve(str(link)) is None

    def test_rejects_a_sibling_directory_with_the_same_prefix(self, library, tmp_path):
        root, resolve, _ = library
        sibling = tmp_path / (root.name + '-backup')
        sibling.mkdir()
        (sibling / 'x.jpg').write_bytes(b'x')

        assert resolve(str(sibling / 'x.jpg')) is None

    def test_rejects_empty(self, library):
        _, resolve, _ = library

        assert resolve('') is None
        assert resolve(None) is None

    def test_the_root_itself_is_inside(self, library):
        root, _, real_root = library

        assert resolve_inside(real_root(), str(root)) == real_root()
