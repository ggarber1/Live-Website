"""`flask cinema-audit`: which films will make the Pi transcode video.

The spec's "favour x264 releases" advice, made checkable. A report, not a
gate: exit 0 whenever Jellyfin answered.
"""
import sys

import click
from flask.cli import with_appcontext

from cinema.client import Jellyfin, JellyfinUnavailable
from cinema.films import LIST_FIELDS, to_film


def films_needing_video_transcode(films):
    return [f for f in films if f['playback'] == 'transcode']


@click.command('cinema-audit')
@with_appcontext
def cinema_audit_command():
    try:
        page = Jellyfin().get_json('/Items', params={
            'IncludeItemTypes': 'Movie', 'Recursive': 'true',
            'Fields': LIST_FIELDS, 'SortBy': 'SortName',
        })
    except (JellyfinUnavailable, RuntimeError) as err:
        click.echo(f"Error: {err}", err=True)
        sys.exit(1)
    films = [to_film(item) for item in page.get('Items', [])]
    heavy = films_needing_video_transcode(films)
    for film in heavy:
        year = f" ({film['year']})" if film['year'] else ''
        click.echo(f"{film['title']}{year}  {film['container']}  "
                   f"{film['video_codec']}/{film['audio_codec']}")
    click.echo(f"{len(heavy)} of {len(films)} films will transcode video")
