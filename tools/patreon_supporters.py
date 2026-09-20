#!/usr/bin/env python3
"""Keep the supporter credits in step with Patreon.

Reads the campaign's member list from the Patreon API, merges it into the
source of truth `data/supporters.json` (one record per Patreon member,
keyed by Patreon's member id, hand-editable) and writes the public
`docs/supporters.json` that the site's credits page and the MisterZine
app read: current supporters and past supporters, names and months only.

Rules of the merge:

- An active patron is a current supporter. First seen, the record takes
  the name Patreon shows and the month the pledge started. After that the
  name is never touched again, so a hand edit (a handle instead of a real
  name) sticks.
- A member whose pledge has ended (former_patron, or gone from the list)
  moves to the past supporters with the month it happened. Nothing is ever
  deleted: the record and its months stay.
- A declined card (declined_patron) is not a cancellation; Patreon keeps
  retrying for a while, so the member stays current.
- A returning supporter comes back to current with the original start
  month kept and the end month cleared.
- Free followers (no pledge: patron_status null) are ignored entirely.
- `hidden: true` on a record keeps that person out of the public file.

Runs with three environment variables: PATREON_ACCESS_TOKEN, and for the
monthly token refresh PATREON_CLIENT_ID, PATREON_CLIENT_SECRET and
PATREON_REFRESH_TOKEN. When the access token has expired the script
refreshes it and, when a GH_SECRETS_TOKEN is present, stores the new pair
back as repository secrets with the gh CLI (the refresh token is single
use, so the new one must be kept). Without network access, `--merge FILE`
feeds it a saved API answer instead.
"""

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://www.patreon.com/api/oauth2/v2"
TOKEN_URL = "https://www.patreon.com/api/oauth2/token"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, "data", "supporters.json")
PUBLIC = os.path.join(ROOT, "docs", "supporters.json")
UA = "misterzine-supporters/1 (+https://misterzine.fyi)"


def month(iso, default):
    """YYYY-MM of an ISO timestamp, or the default when there is none."""
    if not iso:
        return default
    return iso[:7]


def merge(source, members, now_month):
    """Fold Patreon's member list into the source records. Returns the new
    source dict and a list of change lines for the log."""
    recs = dict(source.get("members", {}))
    changes = []
    seen = set()
    for m in members:
        a = m.get("attributes", {})
        status = a.get("patron_status")
        if status is None:
            continue  # a free follower: no pledge, no credit
        mid = m["id"]
        seen.add(mid)
        rec = recs.get(mid)
        if rec is None:
            rec = {
                "name": a.get("full_name", "").strip() or "Anonymous",
                "patreon_name": a.get("full_name", "").strip(),
                "since": month(a.get("pledge_relationship_start"), now_month),
                "until": None,
            }
            recs[mid] = rec
            if status == "former_patron":
                rec["until"] = now_month
                changes.append("past (new record, already ended): " + rec["name"])
            else:
                changes.append("current (new): " + rec["name"])
            continue
        rec["patreon_name"] = a.get("full_name", "").strip() or rec.get("patreon_name", "")
        if status in ("active_patron", "declined_patron"):
            if rec.get("until"):
                rec["until"] = None
                changes.append("current (returned): " + rec["name"])
        elif status == "former_patron":
            if not rec.get("until"):
                rec["until"] = now_month
                changes.append("past: " + rec["name"])
    for mid, rec in recs.items():
        if mid not in seen and not rec.get("until"):
            rec["until"] = now_month
            changes.append("past (gone from Patreon): " + rec["name"])
    out = dict(source)
    out["members"] = dict(sorted(recs.items()))
    return out, changes


def public_view(source, today):
    """The public file: names and months, current then past, A to Z."""
    key = lambda r: r["name"].casefold()
    current, past = [], []
    for rec in source.get("members", {}).values():
        if rec.get("hidden"):
            continue
        if rec.get("until"):
            past.append({"name": rec["name"], "since": rec["since"], "until": rec["until"]})
        else:
            current.append({"name": rec["name"], "since": rec["since"]})
    return {
        "updated": today,
        "current": sorted(current, key=key),
        "past": sorted(past, key=key),
        # hand-maintained, passed through: the people who tested the app
        # before it was ready (the app keeps the same list in its Credits)
        "early_adopters": sorted(source.get("early_adopters", []), key=str.casefold),
    }


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, indent=2) + "\n"
    old = None
    try:
        with open(path, encoding="utf-8") as f:
            old = f.read()
    except FileNotFoundError:
        pass
    if old == text:
        return False
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return True


class TokenExpired(Exception):
    pass


def api_get(url, token):
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token, "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise TokenExpired()
        raise


def fetch_members(token):
    """Every member of the creator's campaign, following the cursor."""
    me = api_get(API + "/identity?include=campaign", token)
    campaign = me["data"]["relationships"]["campaign"]["data"]["id"]
    q = urllib.parse.urlencode({
        "fields[member]": "full_name,patron_status,pledge_relationship_start,last_charge_status",
        "page[count]": "100",
    }, safe="[]")
    url = API + "/campaigns/" + campaign + "/members?" + q
    members = []
    while url:
        page = api_get(url, token)
        members.extend(page.get("data", []))
        url = page.get("links", {}).get("next")
    return members


def refresh_tokens(env):
    body = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": env["PATREON_REFRESH_TOKEN"],
        "client_id": env["PATREON_CLIENT_ID"],
        "client_secret": env["PATREON_CLIENT_SECRET"],
    }).encode()
    req = urllib.request.Request(TOKEN_URL, data=body, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        tok = json.load(r)
    return tok["access_token"], tok["refresh_token"]


def store_secret(name, value, env):
    """Keep a refreshed token: as a repository secret when the workflow has
    a token that may write secrets, otherwise only in the log's advice."""
    gh_token = env.get("GH_SECRETS_TOKEN")
    repo = env.get("GITHUB_REPOSITORY")
    if not gh_token or not repo:
        print("note: no GH_SECRETS_TOKEN, the new %s is not stored; set it by hand" % name, file=sys.stderr)
        return False
    subprocess.run(["gh", "secret", "set", name, "-R", repo], input=value, text=True, check=True,
                   env={**env, "GH_TOKEN": gh_token})
    return True


def run_live(env, today):
    token = env.get("PATREON_ACCESS_TOKEN")
    if not token:
        sys.exit("PATREON_ACCESS_TOKEN is not set")
    try:
        members = fetch_members(token)
    except TokenExpired:
        print("access token expired, refreshing", file=sys.stderr)
        access, refresh = refresh_tokens(env)
        store_secret("PATREON_ACCESS_TOKEN", access, env)
        store_secret("PATREON_REFRESH_TOKEN", refresh, env)
        members = fetch_members(access)
    return members


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--merge", metavar="FILE", help="merge a saved members answer instead of calling Patreon")
    ap.add_argument("--dump", metavar="FILE", help="save the raw members answer here")
    ap.add_argument("--source", default=SOURCE)
    ap.add_argument("--public", default=PUBLIC)
    args = ap.parse_args(argv)
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    if args.merge:
        with open(args.merge, encoding="utf-8") as f:
            members = json.load(f)
            if isinstance(members, dict):
                members = members.get("data", [])
    else:
        members = run_live(os.environ, today)
    if args.dump:
        write_json(args.dump, {"data": members})
    source = load_json(args.source, {"members": {}})
    source, changes = merge(source, members, today[:7])
    for c in changes:
        print(c)
    a = write_json(args.source, source)
    b = write_json(args.public, public_view(source, today))
    pub = public_view(source, today)
    print("supporters: %d current, %d past%s" % (len(pub["current"]), len(pub["past"]),
                                                  "" if (a or b) else " (no change)"))


if __name__ == "__main__":
    main()
