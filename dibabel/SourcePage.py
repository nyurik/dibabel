import re
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from typing import Tuple, List

from pywikiapi import Site

reSite = re.compile(r'^https://(?P<lang>[a-z0-9-_]+)\.(?P<project>[a-z0-9-_]+)\.org/.*', re.IGNORECASE)

# Templates, Modules
allowed_namespaces = {10, 828}

summary_changes_i18n = {
    'en': 'Copying {0} changes by {1}: "{2}" from {3}',
}

summary_restore_i18n = {
    'en': 'Restoring to the current version of {0}',
}


@dataclass
class RevComment:
    user: str
    ts: datetime
    comment: str
    content: str


class TargetPage:
    def __init__(self, site: Site, title: str):
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

    def __str__(self):
        return f'{self.info}/{self.title}'

    def summary_link(self):
        return f'[[mw:{self.title}]]' if self.project == 'mediawiki' else self.__str__()

    def get_content(self) -> Tuple[str, datetime]:
        page, = self.site.query_pages(
            prop=['revisions'],
            rvprop=['content', 'timestamp'],
            titles=self.title)
        if page.ns not in allowed_namespaces:
            raise ValueError(f'Page {self.title} is a prohibited namespace {page.ns}.')
        rev = page.revisions[0]
        return rev.content, datetime.fromisoformat(rev.timestamp.rstrip('Z'))


class SourcePage(TargetPage):
    history: List[RevComment]

    def __init__(self, site: Site, title: str):
        super().__init__(site, title)

        self.history = []
        self.rv_limit = 1
        self.generator = self.site.query(
            prop='revisions',
            rvprop=['user', 'comment', 'timestamp', 'content'],
            rvlimit=self.rv_limit,
            titles=self.title)
        self._update_history(next(self.generator))

    def get_history(self):
        """Get history, progressively increasing the number of pages retrieved in each call (e.g. 1, 5, 25, 25, 25...)
        """
        yield from self.history
        while self.generator:
            try:
                ind = len(self.history)
                self.rv_limit = min(self.rv_limit * 5, 25)
                response = self.generator.send({'rvlimit': self.rv_limit})
                self._update_history(response)
                for i in range(ind, len(self.history)):
                    yield self.history[i]
            except StopIteration:
                self.generator = None

    def _update_history(self, result):
        if not result or not result.pages:
            self.generator = None
        else:
            result = [RevComment(v.user, datetime.fromisoformat(v.timestamp.rstrip('Z')), v.comment.strip(), v.content)
                      for v in result.pages[0].revisions]
            for v in sorted(result, key=lambda v: v.ts):
                self.history.append(v)

    def find_new_revisions(self, content: str) -> Tuple[bool, List[RevComment]]:
        """
        Finds a given content in master revision history, and returns a list of all revisions since then
        :param content: content to find
        :return: if it was found or not, and a list of revisions since then (or all if not found)
        """
        diff_hist = []
        for hist in self.get_history():
            if hist.content == content:
                break
            diff_hist.append(hist)
        else:
            return False, diff_hist
        return True, diff_hist

    def create_summary(self, changes: List[RevComment], lang: str) -> str:
        if changes:
            new_users = {v.user for v in changes}
            fmt = summary_changes_i18n[lang if lang in summary_changes_i18n else 'en']
            # dict keeps the order
            comments = {v.comment: '' for v in changes if v.comment}.keys()
            # Copying {0} changes by {1}: {2} from {3}
            return fmt.format(len(changes), ','.join(new_users),
                              ', '.join(comments), self.summary_link())
        else:
            fmt = summary_restore_i18n[lang if lang in summary_restore_i18n else 'en']
            # Restoring to the current version of {0}
            return fmt.format(self.summary_link())
