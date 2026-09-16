"""Read what the photo table needs from one image file. Pure; never raises."""
import datetime
import logging
import os

from PIL import Image, ImageOps

IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp', '.gif')

EXIF_IFD = 0x8769
DATE_TIME_ORIGINAL = 36867

logger = logging.getLogger(__name__)


def taken_at_from_exif(exif):
    """DateTimeOriginal as a naive datetime, or None if absent or garbage."""
    try:
        raw = exif.get_ifd(EXIF_IFD).get(DATE_TIME_ORIGINAL)
    except Exception:
        return None
    if not raw:
        return None
    try:
        return datetime.datetime.strptime(str(raw).strip(), '%Y:%m:%d %H:%M:%S')
    except ValueError:
        return None


def read_image(path):
    """Width, height (after EXIF rotation), format and taken_at for `path`.

    Returns None when Pillow cannot open the file as an image, which covers
    corrupt files and things merely renamed to look like photos. taken_at is
    the EXIF DateTimeOriginal, or the file's mtime as a naive local datetime.
    """
    try:
        with Image.open(path) as img:
            img_format = (img.format or '').lower()
            exif = img.getexif()
            upright = ImageOps.exif_transpose(img)
            width, height = upright.size
    except Exception as err:
        logger.warning("could not read image %s: %s", path, err)
        return None
    if not img_format:
        return None
    taken = taken_at_from_exif(exif)
    if taken is None:
        taken = datetime.datetime.fromtimestamp(os.stat(path).st_mtime).replace(microsecond=0)
    return {
        'width': width,
        'height': height,
        'format': img_format,
        'taken_at': taken,
    }
