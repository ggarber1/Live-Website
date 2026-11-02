"""Thumbnails, made on first request and cached on disk.

Two sizes only: a grid does not need arbitrary widths, and allowing them
would let one page fill the drive with cache files. The cache lives in a
dot-directory the scanner skips (photos.config.thumbs_dir).
"""
import os

from PIL import Image, ImageOps

from photos.config import thumbs_dir

SIZES = (400, 1200)
QUALITY = 85
# Alpha is flattened onto paper, not black, so a PNG sticker looks at home.
PAPER = (247, 242, 233)


def thumb_path(photo_id, width):
    return os.path.join(thumbs_dir(), f'{photo_id}-{width}.jpg')


def thumbnail(photo_id, source_path, width):
    """Return the cached thumbnail path, making it if needed.

    EXIF orientation is applied so a phone photo shows upright. The image is
    never enlarged: a small original is re-encoded at its own size.
    """
    if width not in SIZES:
        raise ValueError(f'width must be one of {SIZES}')
    target = thumb_path(photo_id, width)
    if os.path.isfile(target):
        return target
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with Image.open(source_path) as img:
        # A JPEG then decodes at 1/2, 1/4 or 1/8 scale instead of full size:
        # a 12 MP phone photo is ~48 MB decoded, enough to bloat a worker.
        # Asking for width x width keeps the short side >= width before
        # rotation, so the result is never smaller than thumbnail() needs.
        img.draft(None, (width, width))
        upright = ImageOps.exif_transpose(img)
        upright.thumbnail((width, width * 2))
        if upright.mode in ('RGBA', 'LA', 'P'):
            flat = Image.new('RGB', upright.size, PAPER)
            flat.paste(upright.convert('RGBA'), mask=upright.convert('RGBA').split()[-1])
            upright = flat
        elif upright.mode != 'RGB':
            upright = upright.convert('RGB')
        # Written beside its final name and renamed, so a crash mid-encode
        # leaves no truncated file that would be served as a thumbnail.
        partial = target + '.part'
        upright.save(partial, 'JPEG', quality=QUALITY, optimize=True)
        os.replace(partial, target)
    return target


def forget(photo_id):
    """Remove every cached size for a photo. Missing files are fine."""
    for width in SIZES:
        try:
            os.remove(thumb_path(photo_id, width))
        except FileNotFoundError:
            pass
