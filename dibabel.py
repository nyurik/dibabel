"""Dibabel keeps wiki resources in sync between languages and sites.

Usage:
  dibabel.py <optfile> [--no-diff] [--show-unknown] [--dry-run] [--force] [--source=<source>] [--site=<site>]... [--item=<id>]...
  dibabel.py --user=<user> --password=<pw> [--no-diff] [--show-unknown] [--dry-run] [--force] [--source=<source>] [--site=<site>]... [--item=<id>]...
  dibabel.py (-h | --help)
  dibabel.py --version

Options:
  -u --user=<user>      Wikipedia bot username.
  -p --password=<pw>    Wikipedia bot password.
  -d --no-diff          Do not show diff for each change.
  -w --show-unknown     Show diff when local revision is not recognized.
  -n --dry-run          Do everything except actually making wiki modifications
  -s --site=<site>...   Limit to the specific site(s), e.g. "en.wikipedia"
  -o --source=<source>  Specify custom source wiki. [default: www.mediawiki]
  -f --force            Overwrite content even if it does not match any of the master's history
  -q --item=<id>...     Wikidata item to process. Multiple ones can be specified.
  -h --help             Show this screen.
  --version             Show version.
"""
import re

from docopt import docopt
from dibabel import Dibabel
from pywikiapi import AttrDict
import json


def parse_arguments(args):
    if args['<optfile>']:
        with open(args['<optfile>'], 'r') as f:
            options = json.load(f, object_hook=AttrDict)
            if not options.user:
                raise ValueError('Options file has no "user" parameter')
            if not options.password:
                raise ValueError('Options file has no "password" parameter')
            user = options.user
            password = options.password
            restrictions = options.restrictions if 'restrictions' in options else {}
    else:
        user = args['--user']
        password = args['--password']
        if not user:
            raise ValueError('"user" parameter is not set')
        if not password:
            raise ValueError('"password" parameter is not set')

    items = args['--item']
    if items and not all((re.match(r'^Q[1-9][0-9]{0,15}$', v) for v in items)):
        raise ValueError('All items must be valid Wikidata ids like Q12345')

    sites = args['--site']
    if sites and not all((re.match(r'^[a-z-]+\.[a-z]+$', v) for v in sites)):
        raise ValueError('All sites must be valid strings like en.wikipedia or www.wikidata')

    if not re.match(r'^[a-z-]+\.[a-z]+$', args['--source']):
        raise ValueError('Source must be valid URL like www.mediawiki')

    return AttrDict(
        user=user,
        password=password,
        restrictions=restrictions,
        show_diff=not args['--no-diff'],
        show_unknown=args['--show-unknown'],
        dry_run=args['--dry-run'],
        force=args['--force'],
        source=args['--source'],
        sites=sites,
        items=items,
    )


if __name__ == '__main__':
    opts = parse_arguments(docopt(__doc__, version='DiBabel 0.1'))
    Dibabel(opts).run()
