import io
import os

import pytest
from PIL import Image

import photos.upload as upload
from photos.thumbs import thumb_path


@pytest.fixture
def library(monkeypatch, tmp_path):
    monkeypatch.setenv('PHOTOS_DIR', str(tmp_path))
    monkeypatch.delenv('PHOTOS_THUMBS_DIR', raising=False)
    return tmp_path


def jpeg_bytes(size=(60, 40), taken=None):
    buf = io.BytesIO()
    exif = Image.Exif()
    if taken:
        exif.get_ifd(0x8769)[36867] = taken
    Image.new('RGB', size, 'purple').save(buf, 'JPEG', exif=exif.tobytes())
    return buf.getvalue()


def png_bytes():
    buf = io.BytesIO()
    Image.new('RGBA', (10, 10), (255, 0, 0, 128)).save(buf, 'PNG')
    return buf.getvalue()


def post(client, *files):
    data = {'files': [(io.BytesIO(content), name) for name, content in files]}
    return client.post('/api/photos', data=data, content_type='multipart/form-data')


def stored_files(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob('*')
                  if p.is_file() and not any(part.startswith('.') for part in p.parts))


class TestUpload:
    def test_two_jpegs_are_stored_by_date_and_indexed(self, client, writes, library):
        res = post(client, ('one.jpg', jpeg_bytes(taken='2024:07:04 12:30:15')),
                   ('two.jpg', jpeg_bytes(taken='2023:01:02 03:04:05')))

        assert res.status_code == 201, res.get_json()
        body = res.get_json()
        assert [p['id'] for p in body['added']] == [42, 42]
        assert body['rejected'] == []
        files = stored_files(library)
        assert files[0].startswith('2023/01/20230102-030405-') and files[0].endswith('.jpg')
        assert files[1].startswith('2024/07/20240704-123015-')
        assert len(writes.queries) == 2
        assert writes.queries[0][0].strip().startswith('INSERT INTO photo')

    def test_the_response_describes_the_photo_without_its_path(self, client, writes, library):
        res = post(client, ('a.jpg', jpeg_bytes(size=(60, 40))))

        [photo] = res.get_json()['added']
        assert (photo['width'], photo['height'], photo['format']) == (60, 40, 'jpeg')
        assert photo['caption'] is None
        assert 'path' not in photo

    def test_a_png_with_alpha_is_accepted(self, client, writes, library):
        res = post(client, ('sticker.png', png_bytes()))

        assert res.status_code == 201
        assert stored_files(library)[0].endswith('.png')

    def test_a_bad_file_is_rejected_by_name_while_the_good_one_is_kept(self, client, writes, library):
        res = post(client, ('notes.jpg', b'hello'), ('real.jpg', jpeg_bytes()))

        assert res.status_code == 201
        body = res.get_json()
        assert len(body['added']) == 1
        assert body['rejected'] == [{'name': 'notes.jpg', 'reason': 'not an image'}]
        assert len(stored_files(library)) == 1

    def test_all_bad_is_a_400_with_reasons(self, client, writes, library):
        res = post(client, ('notes.jpg', b'hello'))

        assert res.status_code == 400
        assert res.get_json()['rejected'][0]['reason'] == 'not an image'
        assert writes.queries == []

    def test_too_large_is_rejected_without_being_written(self, client, writes, library, monkeypatch):
        monkeypatch.setattr(upload, 'MAX_UPLOAD_BYTES', 500)

        res = post(client, ('big.jpg', jpeg_bytes(size=(400, 400))))

        assert res.status_code == 400
        assert 'MB' in res.get_json()['rejected'][0]['reason']
        assert stored_files(library) == []
        assert not any(p.suffix == '.part' for p in library.rglob('*'))

    def test_heic_is_rejected_with_advice(self, client, writes, library):
        heic = b'\x00\x00\x00\x18ftypheic' + b'\x00' * 100

        res = post(client, ('IMG_0001.heic', heic))

        assert 'JPEG' in res.get_json()['rejected'][0]['reason']

    def test_the_client_filename_cannot_choose_the_path(self, client, writes, library):
        post(client, ('../../etc/passwd.jpg', jpeg_bytes()))

        [stored] = stored_files(library)
        assert 'passwd' not in stored and '..' not in stored
        assert not (library.parent / 'etc').exists()

    def test_no_files_is_a_400(self, client, writes, library):
        res = client.post('/api/photos', data={}, content_type='multipart/form-data')

        assert res.status_code == 400

    def test_no_staging_file_is_left_behind(self, client, writes, library):
        post(client, ('a.jpg', jpeg_bytes()), ('bad.jpg', b'nope'))

        assert list((library / '.uploads').iterdir()) == []


class TestDelete:
    def test_removes_file_thumbnails_and_row(self, client, reads, writes, library):
        path = library / 'a.jpg'
        Image.new('RGB', (300, 200), 'purple').save(path, 'JPEG')
        reads.row = {'path': str(path)}
        client.get('/api/photos/1/thumb?w=400')
        assert os.path.exists(thumb_path(1, 400))

        res = client.delete('/api/photos/1')

        assert res.status_code == 204
        assert not path.exists()
        assert not os.path.exists(thumb_path(1, 400))
        assert writes.queries == [('DELETE FROM photo WHERE id = ?', (1,))]

    def test_a_file_already_gone_still_lets_the_row_go(self, client, reads, writes, library):
        reads.row = {'path': str(library / 'gone.jpg')}

        assert client.delete('/api/photos/1').status_code == 204
        assert writes.queries == [('DELETE FROM photo WHERE id = ?', (1,))]

    def test_a_path_outside_the_library_is_never_removed(self, client, reads, writes, library, tmp_path):
        outside = tmp_path.parent / 'precious.jpg'
        Image.new('RGB', (4, 4)).save(outside, 'JPEG')
        reads.row = {'path': str(outside)}

        client.delete('/api/photos/1')

        assert outside.exists()
        outside.unlink()

    def test_unknown_is_404(self, client, reads, writes, library):
        reads.row = None

        assert client.delete('/api/photos/9').status_code == 404
        assert writes.queries == []
