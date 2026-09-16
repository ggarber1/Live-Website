import os

import pytest
from PIL import Image

from photos.thumbs import SIZES, forget, thumb_path, thumbnail


@pytest.fixture
def library(monkeypatch, tmp_path):
    monkeypatch.setenv('PHOTOS_DIR', str(tmp_path))
    monkeypatch.delenv('PHOTOS_THUMBS_DIR', raising=False)
    return tmp_path


def source(root, name='a.jpg', size=(1600, 1200), mode='RGB', orientation=None):
    path = root / name
    img = Image.new(mode, size, (200, 100, 250) if mode == 'RGB' else (200, 100, 250, 128))
    exif = Image.Exif()
    if orientation:
        exif[0x0112] = orientation
    if name.endswith('.png'):
        img.save(path, 'PNG')
    else:
        img.save(path, 'JPEG', exif=exif.tobytes())
    return str(path)


def test_makes_a_jpeg_no_wider_than_asked_in_the_cache(library):
    out = thumbnail(7, source(library), 400)

    assert out == str(library / '.thumbnails' / '7-400.jpg')
    with Image.open(out) as img:
        assert img.format == 'JPEG'
        assert img.width == 400
        assert img.height == 300


def test_a_portrait_phone_photo_comes_out_upright(library):
    out = thumbnail(7, source(library, size=(1600, 1200), orientation=6), 400)

    with Image.open(out) as img:
        assert (img.width, img.height) == (400, 533)  # w bounds the width; portrait is taller


def test_a_small_original_is_not_enlarged(library):
    out = thumbnail(7, source(library, size=(100, 80)), 400)

    with Image.open(out) as img:
        assert (img.width, img.height) == (100, 80)


def test_transparency_is_flattened_onto_paper_not_black(library):
    out = thumbnail(7, source(library, name='a.png', size=(50, 50), mode='RGBA'), 400)

    with Image.open(out) as img:
        r, g, b = img.getpixel((0, 0))
    assert r > 150 and g > 100 and b > 150, 'a half-transparent purple over paper is light, not dark'


def test_the_second_request_uses_the_cache(library):
    path = source(library)
    first = thumbnail(7, path, 400)
    stamp = os.stat(first).st_mtime_ns
    os.remove(path)  # the source is gone; only the cache can answer

    assert thumbnail(7, path, 400) == first
    assert os.stat(first).st_mtime_ns == stamp


def test_only_the_two_sizes_are_allowed(library):
    with pytest.raises(ValueError):
        thumbnail(7, source(library), 500)


def test_forget_removes_every_size_and_tolerates_absence(library):
    path = source(library)
    for width in SIZES:
        thumbnail(7, path, width)

    forget(7)
    forget(7)

    assert not any(os.path.exists(thumb_path(7, w)) for w in SIZES)


def test_no_partial_file_is_left_behind(library):
    thumbnail(7, source(library), 400)

    assert [n for n in os.listdir(library / '.thumbnails') if n.endswith('.part')] == []
