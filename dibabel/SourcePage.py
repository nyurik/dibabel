import re
from dataclasses import dataclass
from datetime import datetime
from typing import Tuple, List, Dict
from pywikiapi import Site
from itertools import chain
from urllib.parse import quote

from .SiteCache import DiSite
from .utils import list_to_dict_of_sets, parse_page_urls, batches
from .Sparql import Sparql
from .ContentPage import ContentPage

# Find any string that is a template name
# Must be preceded by two {{ (not 3!), must be followed by either "|" or "}", must not include any funky characters
reTemplateName = re.compile(r'((?:^|[^{]){{\s*)([^|{}<>&#:]*[^|{}<>&#: ])(\s*[|}])')


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
        self.generator = self.site.query(
            prop='revisions',
            rvprop=['user', 'comment', 'timestamp', 'content'],
            rvlimit=1,
            rvslots='main',
            titles=self.title)

    def get_history(self):
        """Get history, progressively increasing the number of pages retrieved in each call (e.g. 1, 5, 25, 25, 25...)
        """
        yield from self.history
        while self.generator:
            try:
                ind = len(self.history)
                response = self.generator.send({'rvlimit': min(ind * 5, 25)} if ind > 0 else None)
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

    def find_new_revisions(self, target: ContentPage) -> Tuple[bool, List[RevComment], str]:
        """
        Finds a given content in master revision history, and returns a list of all revisions since then
        :param target: content to find
        :return: if it was found or not, and a list of revisions since then (or all if not found), and the new content
        """
        diff_hist = []
        cur_content = target.get_content()
        desired_content = None
        for hist in self.get_history():
            if hist.content == cur_content:
                break
            adj = self.replace_templates(hist.content, target.site)
            if adj == cur_content:
                break
            if desired_content is None:
                desired_content = adj
            diff_hist.append(hist)
        else:
            return False, diff_hist, desired_content
        return True, diff_hist, desired_content

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

    def replace_templates(self, content: str, target_site: DiSite):
        site_cache = self.site.site_cache
        cache = site_cache.template_map
        templates = set(('Template:' + v[1] for v in reTemplateName.findall(content))).difference(cache)
        self.update_template_cache(site_cache, templates)

        def function(m):
            name = m.group(2)
            fullname = 'Template:' + name
            if fullname in cache and target_site in cache[fullname]:
                name = cache[fullname][target_site].split(':', maxsplit=1)[1]
            return m.group(1) + name + m.group(3)

        return reTemplateName.sub(function, content)

    def update_template_cache(self, site_cache, templates):
        cache = site_cache.template_map
        if templates:
            normalized = {}
            redirects = {}
            for batch in batches(templates, 50):
                res = next(site_cache.primary_site.query(titles=batch, redirects=True))
                if 'normalized' in res:
                    normalized.update({v['from']: v.to for v in res.normalized})
                if 'redirects' in res:
                    redirects.update({v['from']: v.to for v in res.redirects})

            unknowns = set(redirects.values()) \
                .union(set(normalized.values()).difference(redirects.keys())) \
                .union(templates.difference(redirects.keys()).difference(normalized.keys())) \
                .difference(cache)

            vals = " ".join(
                {v: f'<https://www.mediawiki.org/wiki/{quote(v.replace(" ", "_"), ": &=+")}>'
                 for v in unknowns}.values())
            query = f'SELECT ?id ?sl WHERE {{ VALUES ?mw {{ {vals} }} ?mw schema:about ?id. ?sl schema:about ?id. }}'
            query_result = Sparql().query(query)
            res = list_to_dict_of_sets(query_result, key=lambda v: v['id']['value'], value=lambda v: v['sl']['value'])
            for values in res.values():
                key, vals = parse_page_urls(site_cache, values)
                if key in cache:
                    raise ValueError(f'WARNING: Logic error - {key} is already cached')
                cache[key] = vals

            for frm, to in chain(redirects.items(), normalized.items()):
                if to not in cache or frm in cache:
                    raise ValueError(f'WARNING: Logic error - {frm}->{to} cannot be matched with cache')
                cache[frm] = cache[to]

            for t in templates:
                if t not in cache:
                    cache[t] = {}  # Empty dict will avoid replacements
