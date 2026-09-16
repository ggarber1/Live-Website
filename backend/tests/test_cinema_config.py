import pytest

from cinema.config import jellyfin_config


@pytest.fixture
def complete(monkeypatch):
    monkeypatch.setenv('JELLYFIN_URL', 'http://jf.test:8096')
    monkeypatch.setenv('JELLYFIN_API_KEY', 'k')
    monkeypatch.setenv('JELLYFIN_USER_ID', 'u')


def test_reads_the_three_variables(complete):
    assert jellyfin_config() == {'url': 'http://jf.test:8096', 'api_key': 'k', 'user_id': 'u'}


def test_a_trailing_slash_on_the_url_is_dropped(complete, monkeypatch):
    monkeypatch.setenv('JELLYFIN_URL', 'http://jf.test:8096/')

    assert jellyfin_config()['url'] == 'http://jf.test:8096'


@pytest.mark.parametrize('name', ['JELLYFIN_URL', 'JELLYFIN_API_KEY', 'JELLYFIN_USER_ID'])
def test_a_missing_variable_is_named(complete, monkeypatch, name):
    monkeypatch.delenv(name)

    with pytest.raises(RuntimeError) as err:
        jellyfin_config()

    assert name in str(err.value)


def test_blank_counts_as_missing(complete, monkeypatch):
    monkeypatch.setenv('JELLYFIN_API_KEY', '')

    with pytest.raises(RuntimeError):
        jellyfin_config()
