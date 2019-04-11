from pywikiapi import Site, AttrDict
from requests.adapters import HTTPAdapter
from requests import Session
# noinspection PyUnresolvedReferences
from requests.packages.urllib3.util.retry import Retry


class SiteCache:
    def __init__(self, user: str, password: str):
        self.sites = {}
        self.site_tokens = {}
        self.user = user
        self.password = password
        self.session = Session()
        self.session.mount('https://', HTTPAdapter(
            max_retries=Retry(total=3, backoff_factor=0.1, status_forcelist=[500, 502, 503, 504])))

    def get(self, url: str) -> Site:
        try:
            return self.sites[url]
        except KeyError:
            site = Site(f'{url}/w/api.php', session=self.session, json_object_hook=AttrDict)
            site.login(user=self.user, password=self.password, on_demand=True)
            self.sites[url] = site
            return site

    def token(self, site: Site) -> str:
        try:
            return self.site_tokens[site]
        except KeyError:
            token = site.token()
            self.site_tokens[site] = token
            return token
