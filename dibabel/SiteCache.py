from typing import Dict, Any

from pywikiapi import Site, AttrDict
from requests.adapters import HTTPAdapter
from requests import Session
# noinspection PyUnresolvedReferences
from requests.packages.urllib3.util.retry import Retry


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
