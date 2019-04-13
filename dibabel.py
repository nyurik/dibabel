"""Dibabel keeps wiki resources in sync between languages and sites.

Usage:
  dibabel.py <optfile> [--diff] [--dry-run] [--force] [--item=<id>]...
  dibabel.py --user=<user> --password=<pw> [--diff] [--dry-run] [--force] [--item=<id>]...
  dibabel.py (-h | --help)
  dibabel.py --version

Options:
  -u --user=<user>    Wikipedia bot username.
  -p --password=<pw>  Wikipedia bot password.
  -d --diff           Show diff for each change.
  -n --dry-run        Do everything except actually making wiki modifications
  -f --force          Overwrite content even if it does not match any of the master's history
  -q --item=<id>...   Wikidata item to process. Multiple ones can be specified.
  -h --help           Show this screen.
  --version           Show version.
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
    else:
        user = args['--user']
        password = args['--password']
        if not user:
            raise ValueError('"user" parameter is not set')
        if not password:
            raise ValueError('"password" parameter is not set')

    items = args['--item']
    if items and not all((re.match('^Q[1-9][0-9]{0,15}$', v) for v in items)):
        raise ValueError('All items must be valid Wikidata ids like Q12345')

    return AttrDict(
        user=user,
        password=password,
        show_diff=args['--diff'],
        dry_run=args['--dry-run'],
        force=args['--force'],
        items=items,
    )


if __name__ == '__main__':
    opts = parse_arguments(docopt(__doc__, version='DiBabel 0.1'))
    Dibabel(opts).run()
