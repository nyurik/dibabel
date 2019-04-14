import re
from collections import defaultdict
from typing import Iterable

from urllib.parse import unquote

reUrl = re.compile(r'^(?P<site>https://[a-z0-9-_.]+)/wiki/(?P<title>[^?#]+)$', re.IGNORECASE)


def list_to_dict_of_sets(items, key, value=None):
    result = defaultdict(set)
    for item in items:
        k = key(item)
        if k:
            if value: item = value(item)
            result[k].add(item)
    return result


def parse_page_urls(sites, page_urls: Iterable[str], qid=None):
    bad_urls = []
    source = None
    targets = {}
    for url in sorted(page_urls):
        match = reUrl.match(url)
        if not match:
            bad_urls.append(url)
            continue
        site_url = match.group('site')
        title = unquote(match.group('title'))
        if site_url == 'https://www.mediawiki.org':
            source = title
        else:
            targets[sites.getSite(site_url)] = title
    if not source:
        raise ValueError(f'Unable to find source page for {qid}')
    if bad_urls:
        print(f'WARN: unable to parse urls:\n  ' + '\n  '.join(bad_urls))
    return source, targets


def batches(items: Iterable, batch_size: int):
    res = []
    for value in items:
        res.append(value)
        if len(res) >= batch_size:
            yield res
            res = []
    if res:
        yield res
