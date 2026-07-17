"""Search Reddit through the official API with the user's own app keys.

Credentials: .secrets/reddit.json in the MAIN checkout ({"client_id": "...",
"client_secret": ""}) - resolved from any worktree via git-common-dir, never
committed (folder is gitignored), never printed. An empty client_secret means
an "installed app": the installed_client grant is used (no secret needed).

Usage:
  python tools/reddit_search.py "query terms" [--sub MiSTerFPGA] [--limit 10] [--sort relevance|new|top]
  python tools/reddit_search.py --comments POST_ID [--limit 40]

Read-only, public data only. Reddit wants a descriptive UA and modest rates.
"""
import io
import json
import subprocess
import sys
import urllib.parse
import urllib.request
import uuid
from base64 import b64encode
from datetime import datetime, timezone
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
UA = 'windows:misterzine-landscape-research:v1.0 (hand-run research tool)'


def creds_path():
    here = Path.cwd() / '.secrets' / 'reddit.json'
    if here.exists():
        return here
    common = subprocess.run(['git', 'rev-parse', '--git-common-dir'],
                            capture_output=True, text=True).stdout.strip()
    return (Path(common).resolve().parent / '.secrets' / 'reddit.json')


def get_token():
    c = json.loads(creds_path().read_text(encoding='utf-8-sig'))
    cid, sec = c['client_id'].strip(), (c.get('client_secret') or '').strip()
    if sec:
        data = 'grant_type=client_credentials'
    else:  # installed app: no secret by design
        data = ('grant_type=' + urllib.parse.quote('https://oauth.reddit.com/grants/installed_client')
                + '&device_id=' + str(uuid.uuid4()))
    req = urllib.request.Request(
        'https://www.reddit.com/api/v1/access_token', data=data.encode(),
        headers={'Authorization': 'Basic ' + b64encode((cid + ':' + sec).encode()).decode(),
                 'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)['access_token']


def api(token, path, **params):
    params['raw_json'] = 1
    url = 'https://oauth.reddit.com' + path + '?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'Authorization': 'bearer ' + token, 'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def when(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%d')


def main():
    args = sys.argv[1:]
    sub = 'MiSTerFPGA'
    limit = 10
    sort = 'relevance'
    comments_id = None
    query = None
    i = 0
    while i < len(args):
        a = args[i]
        if a == '--sub': sub = args[i + 1]; i += 2
        elif a == '--limit': limit = int(args[i + 1]); i += 2
        elif a == '--sort': sort = args[i + 1]; i += 2
        elif a == '--comments': comments_id = args[i + 1]; i += 2
        else: query = a; i += 1

    tok = get_token()
    print('auth ok')
    if comments_id:
        data = api(tok, f'/r/{sub}/comments/{comments_id}', limit=limit, depth=2, sort='top')
        post = data[0]['data']['children'][0]['data']
        print(f"POST: {post['title']}  [{when(post['created_utc'])}] score {post['score']}")
        print(f"https://old.reddit.com{post['permalink']}")
        if post.get('selftext'):
            print('BODY:', post['selftext'][:1200])
        print('--- top comments:')
        def walk(children, depth=0):
            for ch in children:
                d = ch.get('data', {})
                if ch.get('kind') != 't1':
                    continue
                body = (d.get('body') or '').replace('\n', ' ')[:600]
                print(f"{'  ' * depth}[{d.get('score')}] u/{d.get('author')} {when(d.get('created_utc', 0))}: {body}")
                reps = d.get('replies')
                if isinstance(reps, dict):
                    walk(reps['data']['children'], depth + 1)
        walk(data[1]['data']['children'])
    else:
        res = api(tok, f'/r/{sub}/search', q=query, restrict_sr=1, limit=limit, sort=sort, type='link')
        for ch in res['data']['children']:
            d = ch['data']
            print(f"[{d['score']} pts, {d['num_comments']} cmts, {when(d['created_utc'])}] {d['title']}")
            print(f"   id={d['id']}  https://old.reddit.com{d['permalink']}")
            if d.get('selftext'):
                print('   ', d['selftext'].replace('\n', ' ')[:300])


if __name__ == '__main__':
    main()
