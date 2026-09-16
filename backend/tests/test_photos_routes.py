import os

import pytest
from PIL import Image

PHOTO = {'id': 1, 'taken_at': 'Tue, 15 Sep 2026 09:00:00 GMT', 'width': 40, 'height': 30,
         'format': 'jpeg', 'size_bytes': 100, 'caption': None, 'created_at': ''}


@pytest.fixture
def library(monkeypatch, tmp_path):
    monkeypatch.setenv('PHOTOS_DIR', str(tmp_path))
    monkeypatch.delenv('PHOTOS_THUMBS_DIR', raising=False)
    return tmp_path


def real_photo(root, name='a.jpg', size=(800, 600)):
    path = root / name
    Image.new('RGB', size, 'purple').save(path, 'JPEG')
    return str(path)


class TestListing:
    def test_envelope_newest_first(self, client, reads):
        reads.rows = [PHOTO]
        reads.row = {'n': 1}

        res = client.get('/api/photos')

        assert res.status_code == 200
        body = res.get_json()
        assert body == {'photos': [PHOTO], 'total': 1, 'limit': 60, 'offset': 0}
        query, params = reads.queries[0]
        assert 'ORDER BY taken_at DESC, id DESC' in query
        assert params == (60, 0)

    def test_limit_and_offset(self, client, reads):
        reads.rows = []
        reads.row = {'n': 0}

        client.get('/api/photos?limit=12&offset=24')

        assert reads.queries[0][1] == (12, 24)

    @pytest.mark.parametrize('query', ['limit=0', 'limit=201', 'limit=x', 'offset=-1'])
    def test_bad_paging_is_a_400(self, client, reads, query):
        assert client.get(f'/api/photos?{query}').status_code == 400

    def test_no_response_contains_path(self, client, reads):
        reads.rows = [PHOTO]
        reads.row = {'n': 1}
        assert b'"path"' not in client.get('/api/photos').data

        reads.row = PHOTO
        assert b'"path"' not in client.get('/api/photos/1').data


class TestOne:
    def test_found(self, client, reads):
        reads.row = PHOTO

        res = client.get('/api/photos/1')

        assert res.status_code == 200
        assert res.get_json()['id'] == 1

    def test_unknown(self, client, reads):
        reads.row = None

        res = client.get('/api/photos/9')

        assert res.status_code == 404
        assert 'no photo with id 9' in res.get_json()['error']


class TestCaption:
    def test_sets_it(self, client, writes):
        res = client.put('/api/photos/1', json={'caption': '  the fern  '})

        assert res.status_code == 204
        assert writes.queries == [('UPDATE photo SET caption = ? WHERE id = ?', ('the fern', 1))]

    def test_empty_clears_it(self, client, writes):
        client.put('/api/photos/1', json={'caption': ''})

        assert writes.queries[0][1] == (None, 1)

    def test_unknown_is_404(self, client, writes):
        writes.rowcount = 0

        assert client.put('/api/photos/9', json={'caption': 'x'}).status_code == 404

    def test_non_string_is_400(self, client, writes):
        assert client.put('/api/photos/1', json={'caption': 3}).status_code == 400
        assert writes.queries == []


class TestFile:
    def test_serves_the_original_with_its_type(self, client, reads, library):
        reads.row = {'path': real_photo(library)}

        res = client.get('/api/photos/1/file')

        assert res.status_code == 200
        assert res.mimetype == 'image/jpeg'
        assert res.data[:2] == b'\xff\xd8'

    def test_unknown_id(self, client, reads, library):
        reads.row = None

        assert client.get('/api/photos/9/file').status_code == 404

    def test_a_path_outside_the_library_looks_like_an_unknown_id(self, client, reads, library, tmp_path):
        outside = tmp_path.parent / 'secret.jpg'
        Image.new('RGB', (4, 4)).save(outside, 'JPEG')
        reads.row = {'path': str(outside)}

        res = client.get('/api/photos/1/file')

        assert res.status_code == 404
        assert res.get_json()['error'] == 'no photo with id 1'

    def test_indexed_but_missing_says_so(self, client, reads, library):
        reads.row = {'path': str(library / 'gone.jpg')}

        res = client.get('/api/photos/1/file')

        assert res.status_code == 404
        assert 'missing on disk' in res.get_json()['error']


class TestThumb:
    def test_makes_and_caches_a_jpeg_no_wider_than_asked(self, client, reads, library):
        reads.row = {'path': real_photo(library)}

        res = client.get('/api/photos/1/thumb?w=400')

        assert res.status_code == 200
        assert res.mimetype == 'image/jpeg'
        assert res.headers['Cache-Control'] == 'public, max-age=31536000'
        cached = library / '.thumbnails' / '1-400.jpg'
        assert cached.is_file()
        with Image.open(cached) as img:
            assert img.width == 400

    def test_default_is_the_grid_size(self, client, reads, library):
        reads.row = {'path': real_photo(library)}

        client.get('/api/photos/1/thumb')

        assert (library / '.thumbnails' / '1-400.jpg').is_file()

    def test_the_second_request_does_not_regenerate(self, client, reads, library):
        reads.row = {'path': real_photo(library)}
        client.get('/api/photos/1/thumb?w=1200')
        cached = library / '.thumbnails' / '1-1200.jpg'
        stamp = os.stat(cached).st_mtime_ns

        client.get('/api/photos/1/thumb?w=1200')

        assert os.stat(cached).st_mtime_ns == stamp

    @pytest.mark.parametrize('w', ['500', '0', 'big'])
    def test_other_widths_are_a_400(self, client, reads, library, w):
        reads.row = {'path': real_photo(library)}

        assert client.get(f'/api/photos/1/thumb?w={w}').status_code == 400
