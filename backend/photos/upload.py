"""Accept an uploaded image onto the drive, safely.

The client's filename is never used as a path: the file is written to a
temporary dotfile (which the scanner skips), opened with Pillow to prove it
is an image and to read its date, then renamed into PHOTOS_DIR/YYYY/MM/ under
a name of ours. A failure at any step leaves no file behind.
"""
import os
import secrets

from photos.meta import read_image

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
# Pillow's format name -> the extension we store under.
ALLOWED_FORMATS = {'jpeg': '.jpg', 'png': '.png', 'webp': '.webp', 'gif': '.gif'}
STAGING = '.uploads'


class Rejected(Exception):
    """This file is not going to be kept; the message says why."""


def _looks_like_heic(head):
    # ISO base media files carry 'ftyp' at offset 4 and a brand after it.
    return head[4:8] == b'ftyp' and head[8:12] in (b'heic', b'heix', b'hevc', b'mif1', b'msf1')


def save_upload(root, stream, original_name):
    """Store `stream` under `root`. Returns (path, meta, stat) or raises Rejected."""
    staging = os.path.join(root, STAGING)
    os.makedirs(staging, exist_ok=True)
    temp = os.path.join(staging, f'.{secrets.token_hex(8)}.part')
    size = 0
    try:
        with open(temp, 'wb') as out:
            head = b''
            while True:
                chunk = stream.read(65536)
                if not chunk:
                    break
                if not head:
                    head = chunk[:16]
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise Rejected(f'larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB')
                out.write(chunk)
        if size == 0:
            raise Rejected('empty file')
        if _looks_like_heic(head):
            raise Rejected('HEIC is not supported; export it as JPEG first')
        meta = read_image(temp)
        if meta is None:
            raise Rejected('not an image')
        if meta['format'] not in ALLOWED_FORMATS:
            raise Rejected(f"{meta['format']} is not supported")

        taken = meta['taken_at']
        folder = os.path.join(root, f'{taken.year:04d}', f'{taken.month:02d}')
        os.makedirs(folder, exist_ok=True)
        name = f"{taken.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}{ALLOWED_FORMATS[meta['format']]}"
        final = os.path.join(folder, name)
        os.replace(temp, final)
    except BaseException:
        try:
            os.remove(temp)
        except FileNotFoundError:
            pass
        raise
    return final, meta, os.stat(final)
