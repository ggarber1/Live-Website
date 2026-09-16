import datetime
import os

from PIL import Image

from photos.meta import IMAGE_EXTENSIONS, read_image


def jpeg(path, size=(40, 30), orientation=None, taken=None):
    img = Image.new('RGB', size, 'purple')
    exif = Image.Exif()
    if orientation is not None:
        exif[0x0112] = orientation
    if taken is not None:
        exif.get_ifd(0x8769)[36867] = taken
    img.save(path, 'JPEG', exif=exif.tobytes())
    return path


def test_reads_size_and_format(tmp_path):
    meta = read_image(jpeg(tmp_path / 'a.jpg'))

    assert (meta['width'], meta['height'], meta['format']) == (40, 30, 'jpeg')


def test_exif_rotation_swaps_the_dimensions(tmp_path):
    """A phone photo held upright stores landscape pixels plus orientation 6."""
    meta = read_image(jpeg(tmp_path / 'a.jpg', orientation=6))

    assert (meta['width'], meta['height']) == (30, 40)


def test_taken_at_comes_from_exif(tmp_path):
    meta = read_image(jpeg(tmp_path / 'a.jpg', taken='2024:07:04 12:30:15'))

    assert meta['taken_at'] == datetime.datetime(2024, 7, 4, 12, 30, 15)


def test_taken_at_falls_back_to_mtime(tmp_path):
    path = jpeg(tmp_path / 'a.jpg')
    os.utime(path, (1_700_000_000, 1_700_000_000))

    meta = read_image(path)

    assert meta['taken_at'] == datetime.datetime.fromtimestamp(1_700_000_000)


def test_garbage_exif_date_falls_back_to_mtime(tmp_path):
    path = jpeg(tmp_path / 'a.jpg', taken='not a date')
    os.utime(path, (1_700_000_000, 1_700_000_000))

    assert read_image(path)['taken_at'] == datetime.datetime.fromtimestamp(1_700_000_000)


def test_png_and_webp_are_read(tmp_path):
    Image.new('RGBA', (10, 20), (255, 0, 0, 128)).save(tmp_path / 'a.png')
    Image.new('RGB', (10, 20), 'red').save(tmp_path / 'a.webp')

    assert read_image(tmp_path / 'a.png')['format'] == 'png'
    assert read_image(tmp_path / 'a.webp')['format'] == 'webp'


def test_a_corrupt_file_is_none_not_an_exception(tmp_path):
    (tmp_path / 'a.jpg').write_bytes(b'\xff\xd8\xff' + b'junk' * 10)

    assert read_image(tmp_path / 'a.jpg') is None


def test_a_text_file_renamed_jpg_is_none(tmp_path):
    (tmp_path / 'a.jpg').write_text('hello')

    assert read_image(tmp_path / 'a.jpg') is None


def test_a_missing_file_is_none(tmp_path):
    assert read_image(tmp_path / 'nope.jpg') is None


def test_image_extensions_are_lowercase_with_dots():
    for ext in IMAGE_EXTENSIONS:
        assert ext.startswith('.') and ext == ext.lower()
