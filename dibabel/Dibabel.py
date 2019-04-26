import difflib
import json
import traceback

import time

from typing import List, Dict

from dibabel.SourcePage import SourcePage
from dibabel.utils import parse_page_urls
from .SiteCache import SiteCache
from .ContentPage import ContentPage
from .Sparql import Sparql
from .utils import list_to_dict_of_sets


class Dibabel:

    def __init__(self, opts) -> None:
        self.opts = opts
        self.sites = SiteCache()
        self.i18n = self.get_translation_table()

    def run(self):
        todo = self.find_pages_to_sync()
        print(f'Processing {len(todo)} pages')
        for qid, page_urls in todo.items():
            try:
                self.process_page(qid, page_urls)
            except Exception as err:
                print(f'\n******************** ERROR ********************\nFailed to process {qid}')
                print(''.join(traceback.format_exception(etype=type(err), value=err, tb=err.__traceback__)))
        print('Done')

    def find_pages_to_sync(self) -> Dict[str, List[str]]:
        """
        Find all sitelinks for the pages in Wikidata who's instance-of is Q63090714 (auto-synchronized pages)
        :return: a map of wikidata ID -> list of sitelinks
        """
        items = ''
        if self.opts.items:
            items = f' VALUES ?id {{ wd:{" wd:".join(self.opts.items)} }}'
        query = 'SELECT ?id ?sl WHERE {%%% ?id wdt:P31 wd:Q63090714. ?sl schema:about ?id. }'.replace('%%%', items)
        query_result = Sparql().query(query)
        todo = list_to_dict_of_sets(query_result,
                                    key=lambda v: v['id']['value'][len('http://www.wikidata.org/entity/'):],
                                    value=lambda v: v['sl']['value'])
        return todo

    def process_page(self, qid, page_urls):
        updated = 0
        failed = 0
        unrecognized = 0
        source, targets = parse_page_urls(self.sites, page_urls, qid)
        source = SourcePage(self.sites.primary_site, source)
        print(f'Processing {source} ({qid}) -- {len(targets)} pages')

        for site, title in targets.items():
            target = ContentPage(site, title)
            found, changes, new_content = source.find_new_revisions(target)
            if not changes:
                print(f'{target} is up to date')
                continue
            if found or self.opts.force:
                print(f'------- {"WOULD UPDATE" if self.opts.dry_run else "UPDATING"} {target} -------')
                summary = source.create_summary(changes, target.lang, self.i18n)
                print(summary)
                self.print_diff(new_content, target.get_content())
                if not self.opts.dry_run:
                    if not site.logged_in:
                        site.login(self.opts.user, self.opts.password)
                    res = site('edit',
                               title=title, text=new_content, summary=summary,
                               basetimestamp=target.get_content_ts(), bot=True, minor=True, nocreate=True,
                               token=self.sites.token(site))
                    if res.edit.result != 'Success':
                        print(f'ERROR: Update failed - {res.edit.info if "info" in res.edit else json.dumps(res.edit)}')
                        failed += 1
                    else:
                        updated += 1
                    # TODO: handle edit response
                    time.sleep(15)
                else:
                    print('Running in a dry mode, wiki update is skipped')
            else:
                unrecognized += 1
                print(f'------- SKIPPING unrecognized content in {target} -------')
                self.print_diff(changes[0].content, target.get_content())

        unchanged = len(targets) - updated - unrecognized - failed
        print(f'Done with {source} : {len(targets)} total, {updated} updated, {failed} failed update, '
              f'{unrecognized} have unrecognized content, {unchanged} are up to date.')

    def print_diff(self, new_content, old_content):
        if self.opts.show_diff:
            lines = (
                ('32;107' if s.startswith('+') else
                 '31;107' if s.startswith('-') else
                 '33;107' if s.startswith('@@') else
                 '0', s)
                for s in difflib.unified_diff(old_content.split('\n')[1:-1], new_content.split('\n')[1:-1]))
            print(f'\n  ' + '\n  '.join([f"\x1b[{s[0]}m{s[1].rstrip()}\x1b[0m" for s in lines][2:]) + '\n')

    def get_translation_table(self):
        page = ContentPage(self.sites.getSite('https://commons.wikimedia.org'), 'Data:I18n/DiBabel.tab')
        i18n, = (v for k, v in json.loads(page.get_content())['data'] if k == 'edit_summary')
        return i18n
