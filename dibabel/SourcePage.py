from dataclasses import dataclass
from datetime import datetime
from typing import Tuple, List, Dict
from pywikiapi import Site

from .ContentPage import ContentPage


@dataclass
class RevComment:
    user: str
    ts: datetime
    comment: str
    content: str


class SourcePage(ContentPage):
    history: List[RevComment]

    def __init__(self, site: Site, title: str):
        super().__init__(site, title)

        self.history = []
        self.rv_limit = 1
        self.generator = self.site.query(
            prop='revisions',
            rvprop=['user', 'comment', 'timestamp', 'content'],
            rvlimit=self.rv_limit,
            rvslots='main',
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
            result = [RevComment(v.user, datetime.fromisoformat(v.timestamp.rstrip('Z')), v.comment.strip(),
                                 v.slots.main.content)
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

    def create_summary(self, changes: List[RevComment], lang: str, summary_i18n: Dict[str, str]) -> str:
        summary_link = f'[[mw:{self.title}]]' if self.project == 'mediawiki' else self.__str__()
        if changes:
            new_users = {v.user for v in changes}
            # dict keeps the order
            comments = {v.comment: '' for v in changes if v.comment}.keys()
            # Copying $1 changes by $2: "$3" from $4
            text = summary_i18n[lang if lang in summary_i18n else 'en']
            text = text.replace('$1', str(len(changes)))
            text = text.replace('$2', ','.join(new_users))
            text = text.replace('$3', ', '.join(comments))
            text = text.replace('$4', summary_link)

            return self.site(
                action='expandtemplates',
                text=text,
                prop='wikitext',
            ).expandtemplates.wikitext
        else:
            # Restoring to the current version of {0}
            return f'Restoring to the current version of {summary_link}'
