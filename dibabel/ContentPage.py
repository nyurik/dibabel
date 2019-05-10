import re
from datetime import datetime

from .SiteCache import DiSite

reSite = re.compile(r'^https://(?P<lang>[a-z0-9-_]+)\.(?P<project>[a-z0-9-_]+)\.org/.*', re.IGNORECASE)


class ContentPage:
    def __init__(self, site: DiSite, title: str):
        self.site = site
        self.title = title
        m = reSite.match(site.url)
        if not m:
            raise ValueError(f'*************** WARN: unable to parse {site.url}')
        self.lang = m.group('lang')
        self.project = m.group('project')
        if self.lang != 'www':
            self.info = f"{self.lang}.{self.project}"
        else:
            self.info = m.group('project')
        self._content = None
        self._content_ts = None

    def get_content(self) -> str:
        self._get_content()
        return self._content

    def get_content_ts(self) -> str:
        self._get_content()
        return self._content_ts

    def _get_content(self):
        if self._content is not None:
            return
        props = ['content', 'timestamp']
        if self.site.has_flagged_revisions():
            props.append('flagged')
            props.append('ids')
        page, = self.site.query_pages(
            prop=['revisions'],
            rvprop=props,
            rvslots='main',
            titles=self.title)
        if 'missing' in page:
            self._content = False
            self._content_ts = False
            return
        rev = page.revisions[0]
        # if self.site.has_flagged_revisions():
        #     TODO
        self._content = rev.slots.main.content
        self._content_ts = datetime.fromisoformat(rev.timestamp.rstrip('Z'))

    def __str__(self):
        return f'{self.info}.org/wiki/{self.title}'
