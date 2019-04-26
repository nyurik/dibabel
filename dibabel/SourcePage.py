import re
from dataclasses import dataclass
from datetime import datetime
from typing import Tuple, List, Dict
from pywikiapi import Site

from .SiteCache import DiSite
from .ContentPage import ContentPage

# Find any string that is a template name
# Must be preceded by two {{ (not 3!), must be followed by either "|" or "}", must not include any funky characters
reTemplateName = re.compile(r'''((?:^|[^{]){{\s*)([^|{}<>&#:]*[^|{}<>&#: ])(\s*[|}])''')

# Find any require('Module:name')
# must be preceded by a space or an operation like = or a comma.
reModuleName = re.compile(r'''((?:^|\s|=|,|\()require\s*\(\s*)('[^']+'|"[^"]+")(\s*\))''')


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
        self.is_module = self.title.startswith('Module:')
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
            adj = self.replace_templates(hist.content, target.site)
            if desired_content is None:
                # Comparing current revision of the master page
                desired_content = adj
                # Latest revision must match adjusted content
                if adj == cur_content:
                    # Latest matches what we expect, nothing to do
                    break
                elif hist.content == cur_content:
                    # local template was renamed without any changes in master, re-add last revision
                    diff_hist.append(hist)
                    break
            elif adj == cur_content or hist.content == cur_content:
                # One of the previous revisions matches current state of the target
                break
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

            res = self.site(
                action='expandtemplates',
                text=text,
                prop='wikitext')

            # for some reason template expansions add \n in some places
            return res.expandtemplates.wikitext.replace('\n', '')
        else:
            # Restoring to the current version of {0}
            return f'Restoring to the current version of {summary_link}'

    def replace_templates(self, content: str, target_site: DiSite):
        site_cache = self.site.site_cache
        cache = site_cache.template_map

        if self.is_module:
            titles = (v[1] for v in reModuleName.findall(content))
        else:
            titles = ('Template:' + v[1] for v in reTemplateName.findall(content))

        self.site.site_cache.update_template_cache(titles)

        if self.is_module:

            def sub_module(m):
                name = m.group(2)
                fullname = name[1:-1]  # strip first and last quote symbol
                if fullname in cache and target_site in cache[fullname]:
                    repl = cache[fullname][target_site]
                    quote = name[0]
                    if quote not in repl:
                        name = quote + repl + quote
                    else:
                        quote = '"' if quote == "'" else "'"
                        if quote not in repl:
                            name = quote + repl + quote
                        else:
                            name = "'" + repl.replace("'", "\\'") + "'"
                else:
                    print(f'WARNING: Dependency {fullname} might not exist on {target_site}')

                return m.group(1) + name + m.group(3)

            return reModuleName.sub(sub_module, content)

        else:

            def sub_template(m):
                name = m.group(2)
                magicwords, magicprefixes = self.site.get_magicwords()
                if name not in magicwords and not any(v for v in magicprefixes if name.startswith(v)):
                    fullname = 'Template:' + name
                    if fullname in cache and target_site in cache[fullname]:
                        name = cache[fullname][target_site].split(':', maxsplit=1)[1]
                    else:
                        print(f'WARNING: Dependency {fullname} might not exist on {target_site}')
                return m.group(1) + name + m.group(3)

            return reTemplateName.sub(sub_template, content)
