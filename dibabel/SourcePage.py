import re
from dataclasses import dataclass
from datetime import datetime
from typing import Tuple, List, Dict, Set, Union
from pywikiapi import Site

from .SiteCache import DiSite
from .ContentPage import ContentPage

# Find any string that is a template name
# Must be preceded by two {{ (not 3!), must be followed by either "|" or "}", must not include any funky characters
reTemplateName = re.compile(r'''((?:^|[^{]){{\s*)([^|{}<>&#:]*[^|{}<>&#: ])(\s*[|}])''')

# Find any require('Module:name') and mw.loadData('Module:name')
# must be preceded by a space or an operation like = or a comma.
reModuleName = re.compile(r'''((?:^|\s|=|,|\()(?:require|mw\.loadData)\s*\(\s*)('[^']+'|"[^"]+")(\s*\))''')

well_known_lua_modules = {
    'libraryUtil'
}


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
                result = self.generator.send({'rvlimit': min(ind * 5, 25)} if ind > 0 else None)

                if not result or not result.pages:
                    self.generator = None
                else:
                    result = [RevComment(v.user, datetime.fromisoformat(v.timestamp.rstrip('Z')), v.comment.strip(),
                                         v.slots.main.content)
                              for v in result.pages[0].revisions]
                    for v in sorted(result, key=lambda v: v.ts, reverse=True):
                        self.history.append(v)

                for i in range(ind, len(self.history)):
                    yield self.history[i]
            except StopIteration:
                self.generator = None

    def find_new_revisions(self, target: ContentPage) -> \
            Tuple[bool, List[RevComment], Union[str, None], Union[Set[str], None], Union[Set[str], None]]:
        """
        Finds a given content in master revision history, and returns a list of all revisions since then
        :param target: content to find
        :return: If the target's current revision was found in source's history, List of revisions changed since then,
                 the new content for the target, and a set of the missing templates/modules
        """
        diff_hist = []
        desired_content = None
        missing_dependencies = None
        nonshared_dependencies = None

        cur_content = target.get_content()
        if not cur_content:
            return False, diff_hist, desired_content, missing_dependencies, nonshared_dependencies

        found = True
        for hist in self.get_history():
            adj, missing, nonshared = self.replace_templates(hist.content, target.site)
            if desired_content is None:
                # Comparing current revision of the master page
                desired_content = adj
                missing_dependencies = missing
                nonshared_dependencies = nonshared
                # Latest revision must match adjusted content
                if adj == cur_content or missing_dependencies:
                    # Latest matches what we expect - nothing to do,
                    # or there are missing dependent modules/templates, stop
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
            found = False

        return found, diff_hist, desired_content, missing_dependencies, nonshared_dependencies

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

    def replace_templates(self, content: str, target_site: DiSite) -> Tuple[str, set, set]:
        site_cache = self.site.site_cache
        cache = site_cache.template_map
        missing_dependencies = set()
        nonshared_dependencies = set()

        if self.is_module:
            titles = (v for v in (vv[1][1:-1] for vv in reModuleName.findall(content))
                      if v not in well_known_lua_modules)
        else:
            titles = ('Template:' + v[1] for v in reTemplateName.findall(content))

        self.site.site_cache.update_template_cache(titles)

        if self.is_module:

            def sub_module(m):
                name = m.group(2)
                fullname = name[1:-1]  # strip first and last quote symbol
                if fullname in cache and 'not-shared' in cache[fullname]:
                    nonshared_dependencies.add(fullname)
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
                elif fullname not in well_known_lua_modules:
                    missing_dependencies.add(fullname)

                return m.group(1) + name + m.group(3)

            new_content = reModuleName.sub(sub_module, content)

        else:

            def sub_template(m):
                name = m.group(2)
                magic_words, magic_prefixes = self.site.get_magicwords()
                if name not in magic_words and not any(v for v in magic_prefixes if name.startswith(v)):
                    fullname = 'Template:' + name
                    if fullname in cache and 'not-shared' in cache[fullname]:
                        nonshared_dependencies.add(fullname)
                    if fullname in cache and target_site in cache[fullname]:
                        name = cache[fullname][target_site].split(':', maxsplit=1)[1]
                    else:
                        missing_dependencies.add(fullname)
                return m.group(1) + name + m.group(3)

            new_content = reTemplateName.sub(sub_template, content)

        return new_content, missing_dependencies, nonshared_dependencies
