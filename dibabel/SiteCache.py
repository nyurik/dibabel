from itertools import chain
from urllib.parse import quote

from typing import Dict, Any, Iterable

from pywikiapi import Site, AttrDict
from requests.adapters import HTTPAdapter
from requests import Session
# noinspection PyUnresolvedReferences
from requests.packages.urllib3.util.retry import Retry

from dibabel.Sparql import Sparql
from dibabel.utils import batches, list_to_dict_of_sets, parse_page_urls


class DiSite(Site):

    def __init__(self, site_cache: 'SiteCache', url: str):
        super().__init__(url, session=site_cache.session, json_object_hook=AttrDict)
        self.site_cache = site_cache
        self.flagged_revisions = None

    def has_flagged_revisions(self):
        if self.flagged_revisions is None:
            # Have not initialized yet
            res = next(self.query(meta='siteinfo', siprop='extensions'))
            self.flagged_revisions = \
                bool([v for v in res.extensions if 'descriptionmsg' in v and v.descriptionmsg == 'flaggedrevs-desc'])
            if self.flagged_revisions:
                print(f'{self} has enabled flagged revisions')
        return self.flagged_revisions


class SiteCache:
    # Template name -> dict( language code -> localized template name )
    template_map: Dict[str, Dict[DiSite, str]]

    def __init__(self):
        self.template_map = {}
        self.sites = {}
        self.site_tokens = {}
        self.session = Session()
        self.session.mount('https://', HTTPAdapter(
            max_retries=Retry(total=3, backoff_factor=0.1, status_forcelist=[500, 502, 503, 504])))

        self.primary_site = self.getSite('https://www.mediawiki.org')

    def getSite(self, url: str) -> DiSite:
        try:
            return self.sites[url]
        except KeyError:
            site = DiSite(self, f'{url}/w/api.php')
            self.sites[url] = site
            return site

    def token(self, site: DiSite) -> str:
        try:
            return self.site_tokens[site]
        except KeyError:
            token = site.token()
            self.site_tokens[site] = token
            return token

    def update_template_cache(self, titles: Iterable[str]):
        cache = self.template_map
        titles = set(titles).difference(cache)
        if not titles:
            return

        # Ask mediawiki.org to resolve titles
        normalized = {}
        redirects = {}
        for batch in batches(titles, 50):
            res = next(self.primary_site.query(titles=batch, redirects=True))
            if 'normalized' in res:
                normalized.update({v['from']: v.to for v in res.normalized})
            if 'redirects' in res:
                redirects.update({v['from']: v.to for v in res.redirects})

        unknowns = set(redirects.values()) \
            .union(set(normalized.values()).difference(redirects.keys())) \
            .union(titles.difference(redirects.keys()).difference(normalized.keys())) \
            .difference(cache)

        vals = " ".join(
            {v: f'<https://www.mediawiki.org/wiki/{quote(v.replace(" ", "_"), ": &=+")}>'
             for v in unknowns}.values())
        query = f'SELECT ?id ?sl WHERE {{ VALUES ?mw {{ {vals} }} ?mw schema:about ?id. ?sl schema:about ?id. }}'
        query_result = Sparql().query(query)
        res = list_to_dict_of_sets(query_result, key=lambda v: v['id']['value'], value=lambda v: v['sl']['value'])
        for values in res.values():
            key, vals = parse_page_urls(self, values)
            if key in cache:
                raise ValueError(f'WARNING: Logic error - {key} is already cached')
            cache[key] = vals

        for frm, to in chain(redirects.items(), normalized.items()):
            if to not in cache or frm in cache:
                raise ValueError(f'WARNING: Logic error - {frm}->{to} cannot be matched with cache')
            cache[frm] = cache[to]

        for t in titles:
            if t not in cache:
                cache[t] = {}  # Empty dict will avoid replacements
