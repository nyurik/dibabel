"""Dibabel keeps wiki resources in sync between languages and sites.

Usage:
  dibabel.py <optfile> [--diff] [--dry-run] [--force] [--item=<id>]...
  dibabel.py (-h | --help)
  dibabel.py --version

Options:
  -d --diff         Show diff for each change.
  -n --dry-run      Do everything except actually making wiki modifications
  -f --force        Overwrite content even if it does not match any of the master's history
  -q --item=<id>... Wikidata item to process. Multiple ones can be specified.
  -h --help         Show this screen.
  --version         Show version.
"""
import re

from docopt import docopt
from dibabel import Dibabel
from pywikiapi import AttrDict
import json


def parse_arguments(args):
    with open(args['<optfile>'], 'r') as f:
        options = json.load(f, object_hook=AttrDict)
        if not options.user:
            raise ValueError('Options file has no "user" parameter')
        if not options.password:
            raise ValueError('Options file has no "password" parameter')

        items = args['--item']
        if items and not all((re.match('^Q[1-9][0-9]{0,15}$', v) for v in items)):
            raise ValueError('All items must be valid Wikidata ids like Q12345')

        return AttrDict(
            user=options.user,
            password=options.password,
            show_diff=args['--diff'] or ('diff' in options and options.diff),
            dry_run=args['--dry-run'],
            force=args['--force'],
            items=items,
        )


if __name__ == '__main__':
    opts = parse_arguments(docopt(__doc__, version='DiBabel 0.1'))
    Dibabel(opts).run()
