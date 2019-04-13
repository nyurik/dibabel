import difflib
import json

import time

from typing import List, Dict

from .SiteCache import SiteCache
from .SourcePage import SourcePage
from .ContentPage import ContentPage
from .Sparql import Sparql
from .utils import list_to_dict_of_lists
import re

reUrl = re.compile(r'^(?P<site>https://[a-z0-9-_.]+)/wiki/(?P<title>[^?#]+)$', re.IGNORECASE)


class Dibabel:

    def __init__(self, opts) -> None:
        self.opts = opts
        self.sparql = Sparql()
        self.sites = SiteCache()
        self.i18n = self.get_translation_table()

    def run(self):
        todo = self.find_pages_to_sync()
        print(f'Processing {len(todo)} pages')
        for qid, page_urls in todo.items():
            try:
                self.process_page(qid, page_urls)
            except Exception as err:
                print(f'\n******************** ERROR ********************\nFailed to process {qid}: {err}')

        print('Done')

    def find_pages_to_sync(self) -> Dict[str, List[str]]:
        """
        Find all sitelinks for the pages in Wikidata who's instance-of is Q63090714 (auto-synchronized pages)
        :return: a map of wikidata ID -> list of sitelinks
        """
        items = ''
        if self.opts.items:
            items = f' VALUES ?id {{ wd:{" wd:".join(self.opts.items)} }}'
        sparql = 'SELECT ?id ?sl WHERE {%%% ?id wdt:P31 wd:Q63090714. ?sl schema:about ?id. }'.replace('%%%', items)
        query_result = self.sparql.query(sparql)
        todo = list_to_dict_of_lists(query_result,
                                     key=lambda v: v['id']['value'][len('http://www.wikidata.org/entity/'):],
                                     value=lambda v: v['sl']['value'])
        return todo

    def process_page(self, qid, page_urls):
        updated = 0
        unrecognized = 0
        source, targets, bad_urls = self.parse_page_urls(page_urls, qid)
        print(f'Processing {source} ({qid}) -- {len(targets)} pages')
        if bad_urls:
            print(f'WARN: unable to parse urls:\n  ' + '\n  '.join(bad_urls))

        for target in targets:
            old_content, old_ts = target.get_content()
            found, changes = source.find_new_revisions(old_content)
            if not changes:
                print(f'{target} is up to date')
                continue
            if found or self.opts.force:
                updated += 1
                print(f'------- {"WOULD UPDATE" if self.opts.dry_run else "UPDATING"} {target} -------')
                summary = source.create_summary(changes, target.lang, self.i18n)
                print(summary)
                new_content = changes[0].content
                self.print_diff(new_content, old_content)
                if not self.opts.dry_run:
                    if not target.site.logged_in:
                        target.site.login(self.opts.user, self.opts.password)
                    res = target.site('edit',
                                      title=target.title, text=new_content, summary=summary,
                                      basetimestamp=old_ts, bot=True, minor=True, nocreate=True,
                                      token=self.sites.token(target.site))
                    # TODO: handle edit response
                    time.sleep(15)
                else:
                    print('Running in a dry mode, wiki update is skipped')
            else:
                unrecognized += 1
                print(f'------- SKIPPING unrecognized content in {target} -------')
                self.print_diff(changes[0].content, old_content)

        print(f'Done with {source} : {len(targets)} total, {updated} updated, '
              f'{unrecognized} have unrecognized content, {len(targets) - updated - unrecognized} are up to date.')

    def print_diff(self, new_content, old_content):
        if self.opts.show_diff:
            lines = (
                ('32;107' if s.startswith('+') else
                 '31;107' if s.startswith('-') else
                 '33;107' if s.startswith('@@') else
                 '0', s)
                for s in difflib.unified_diff(old_content.split('\n')[1:-1], new_content.split('\n')[1:-1]))
            print(f'\n  ' + '\n  '.join([f"\x1b[{s[0]}m{s[1].rstrip()}\x1b[0m" for s in lines][2:]) + '\n')

    def parse_page_urls(self, page_urls: List[str], qid: str):
        bad_urls = []
        source = None
        targets = []
        for url in page_urls:
            match = reUrl.match(url)
            if not match:
                bad_urls.append(url)
                continue
            site_url = match.group('site')
            if site_url == 'https://www.mediawiki.org':
                source = SourcePage(self.sites.get(site_url), match.group('title'))
            else:
                targets.append(ContentPage(self.sites.get(site_url), match.group('title')))
        if not source:
            raise ValueError(f'Unable to find source page for {qid}')
        return source, targets, bad_urls

    def get_translation_table(self):
        page = ContentPage(self.sites.get('https://commons.wikimedia.org'), 'Data:I18n/DiBabel.tab')
        i18n, = (v for k, v in json.loads(page.get_content()[0])['data'] if k == 'edit_summary')
        return i18n
