import re
import urllib.parse
from datetime import datetime
from typing import Tuple

from .SiteCache import DiSite

reSite = re.compile(r'^https://(?P<lang>[a-z0-9-_]+)\.(?P<project>[a-z0-9-_]+)\.org/.*', re.IGNORECASE)


class ContentPage:
    def __init__(self, site: DiSite, title: str):
        self.site = site
        self.title = urllib.parse.unquote(title)
        m = reSite.match(site.url)
        if not m:
            raise ValueError(f'*************** WARN: unable to parse {site.url}')
        self.lang = m.group('lang')
        self.project = m.group('project')
        if self.lang != 'www':
            self.info = f"{self.lang}.{self.project}"
        else:
            self.info = m.group('project')

    def get_content(self) -> Tuple[str, datetime]:
        props = ['content', 'timestamp']
        if self.site.has_flagged_revisions():
            props.append('flagged')
            props.append('ids')
        page, = self.site.query_pages(
            prop=['revisions'],
            rvprop=props,
            rvslots='main',
            titles=self.title)
        rev = page.revisions[0]
        # if self.site.has_flagged_revisions():
        #     TODO
        return rev.slots.main.content, datetime.fromisoformat(rev.timestamp.rstrip('Z'))

    def __str__(self):
        return f'{self.info}.org/wiki/{self.title}'
