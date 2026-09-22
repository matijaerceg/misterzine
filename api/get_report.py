"""Fetch, list or delete the reports players send from MisterZine.

    python api/get_report.py K7Q2             print the report and keep a copy
    python api/get_report.py --list           the reports of the last 30 days
    python api/get_report.py --delete K7Q2

The admin token is the Worker secret REPORTS_TOKEN. It is read from
MZ_REPORTS_TOKEN, else from .secrets/reports.json ({"token": "..."}) in the
main checkout. Copies are saved under .secrets/reports/, which git ignores:
a report describes a player's card and never belongs in the repository.
The service deletes every report 30 days after it arrives, and a code can
be drawn again after that: check the upload date printed above a report
against when the player posted its code.
"""
import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import urllib.error
import urllib.request

API = 'https://api.misterzine.fyi'
UA = 'misterzine-get-report/1'


def main_checkout():
    """The main checkout's root, also when run from a worktree."""
    here = pathlib.Path(__file__).resolve().parent
    try:
        common = subprocess.check_output(['git', 'rev-parse', '--path-format=absolute', '--git-common-dir'],
                                         cwd=here, text=True).strip()
        return pathlib.Path(common).parent
    except (OSError, subprocess.CalledProcessError):
        return here.parent


def token(secrets):
    if os.environ.get('MZ_REPORTS_TOKEN'):
        return os.environ['MZ_REPORTS_TOKEN']
    path = secrets / 'reports.json'
    try:
        return json.loads(path.read_text(encoding='utf-8'))['token']
    except (OSError, KeyError, ValueError):
        sys.exit('No admin token: set MZ_REPORTS_TOKEN or write {"token": "..."} to ' + str(path))


def code_of(s):
    """What a person types, as the service stores it (Crockford base32)."""
    c = re.sub(r'[\s-]', '', s.upper()).replace('I', '1').replace('L', '1').replace('O', '0')
    if not re.fullmatch(r'[0-9A-HJKMNP-TV-Z]{4}', c):
        sys.exit('Not a report code: ' + s)
    return c


def call(method, path, tok, api):
    req = urllib.request.Request(api + path, method=method,
                                 headers={'Authorization': 'Bearer ' + tok, 'User-Agent': UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read(), r.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('code', nargs='?', help='the code the player posted, e.g. K7Q2')
    p.add_argument('--list', action='store_true', help='list the reports of the last 30 days')
    p.add_argument('--delete', metavar='CODE', help='delete one report now')
    p.add_argument('--api', default=API, help=argparse.SUPPRESS)
    a = p.parse_args()
    secrets = main_checkout() / '.secrets'
    tok = token(secrets)
    if a.list:
        status, body, _ = call('GET', '/reports', tok, a.api)
        if status != 200:
            sys.exit('HTTP %d: %s' % (status, body.decode(errors='replace')))
        rows = json.loads(body)['reports']
        for r in rows:
            print('%s  %s  %6d bytes  %s' % (r['code'], r['uploaded'][:16].replace('T', ' '), r['size'], r['app']))
        print('%d report(s)' % len(rows))
    elif a.delete:
        code = code_of(a.delete)
        status, body, _ = call('DELETE', '/reports/' + code, tok, a.api)
        print('deleted' if status == 204 else 'HTTP %d: %s' % (status, body.decode(errors='replace')))
    elif a.code:
        code = code_of(a.code)
        status, body, headers = call('GET', '/reports/' + code, tok, a.api)
        if status == 404:
            sys.exit('No report %s (wrong code, or older than 30 days)' % code)
        if status != 200:
            sys.exit('HTTP %d: %s' % (status, body.decode(errors='replace')))
        uploaded = headers.get('X-Report-Uploaded', '')
        print('-- %s, uploaded %s UTC' % (code, uploaded[:16].replace('T', ' ')), file=sys.stderr)
        out = secrets / 'reports' / ('%s-%s.txt' % (code, uploaded[:10].replace('-', '')))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(body)
        sys.stdout.write(body.decode('utf-8', errors='replace'))
        print('\n-- saved to %s' % out, file=sys.stderr)
    else:
        p.print_help()


if __name__ == '__main__':
    main()
