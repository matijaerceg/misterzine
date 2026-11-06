"""Match official MiSTer builds to repositories listed by the distribution itself."""
import hashlib
import json
import re
import subprocess
from collections import defaultdict
from pathlib import PurePosixPath
from urllib.parse import unquote

WIKI = "https://raw.githubusercontent.com/wiki/MiSTer-devel/Wiki_MiSTer/Cores.md"
DIST = "MiSTer-devel/Distribution_MiSTer"


def wiki_projects(markdown):
    projects = set()
    section = None
    for line in markdown.splitlines():
        if "arcade_list_start" in line:
            section = "arcade"
        elif "cores_list_start" in line:
            section = "system"
        elif "_list_end" in line:
            section = None
        elif section and line.lstrip().startswith("|"):
            first_cell = line.split("|")[1]
            match = re.search(r"\]\(https://github\.com/(MiSTer-devel/[\w.-]+(?:/tree/[\w./-]+)?)\s*\)", first_cell, re.I)
            if match:
                projects.add((section, match[1].rstrip("/")))
    if {section for section, _ in projects} != {"arcade", "system"}:
        raise ValueError("The official core list is missing a section")
    return sorted(projects)


def github_trees(requests):
    """Read directory entries and git blob IDs in batches, without downloading cores."""
    trees = []
    for start in range(0, len(requests), 24):
        fields = []
        batch = requests[start:start + 24]
        for i, (repo, ref, directory) in enumerate(batch):
            owner, name = repo.split("/")
            expression = json.dumps(ref + ":" + directory)
            fields.append(f"r{i}:repository(owner:{json.dumps(owner)},name:{json.dumps(name)})"
                          "{defaultBranchRef{name} dir:object(expression:" + expression +
                          "){... on Tree{entries{name oid type}}}}")
        payload = json.dumps({"query": "{" + " ".join(fields) + "}"})
        proc = subprocess.run(["gh", "api", "graphql", "--input", "-"], input=payload,
                              text=True, encoding="utf-8", capture_output=True, timeout=90)
        if proc.returncode:
            raise RuntimeError("GitHub directory lookup failed: " + proc.stderr.strip()[:350])
        result = json.loads(proc.stdout)
        if result.get("errors"):
            raise RuntimeError("Incomplete GitHub directory lookup")
        for i in range(len(batch)):
            entry = result["data"][f"r{i}"]
            trees.append((entry["defaultBranchRef"]["name"], (entry["dir"] or {}).get("entries", [])))
    return trees


def refresh_official(db, cache_path, http_get, log=print, read_trees=github_trees):
    # The pinned distribution commit connects the feed's MD5 to a Git blob ID.
    # Never compare a moving branch to a snapshot from another revision.
    base = (db.get("base_files_url") or "").rstrip("/")
    revision = re.fullmatch(r"https://raw\.githubusercontent\.com/MiSTer-devel/Distribution_MiSTer/([a-f0-9]{40})", base, re.I)
    if not revision:
        raise ValueError("Official distribution did not supply a pinned revision")
    builds = {p: v["hash"] for p, v in db["files"].items()
              if p.lower().endswith(".rbf") and p.lower().startswith(("_arcade/cores/", "_console/", "_computer/", "_other/"))
              and (not v.get("url") or unquote(v["url"]) == base + "/" + p)}
    if not builds:
        raise ValueError("Official feed contains no core files")
    projects = wiki_projects(http_get(WIKI).decode("utf-8"))
    signature = hashlib.sha256(json.dumps([projects, builds], sort_keys=True).encode()).hexdigest()
    old = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    if old.get("signature") == signature and all(len(v[1]) == 1 for v in old["files"].values()):
        return
    directories = sorted({str(PurePosixPath(path).parent) for path in builds})
    dist_trees = read_trees([(DIST, revision[1], folder) for folder in directories])
    blobs = {folder + "/" + e["name"]: e["oid"] for folder, (_, entries) in zip(directories, dist_trees)
             for e in entries if e["type"] == "blob"}
    if builds.keys() - blobs.keys():
        raise ValueError("Pinned distribution tree is missing shipped cores")

    requests = []
    for _, project in projects:
        repo, _, location = project.partition("/tree/")
        branch, _, subdir = location.partition("/")
        directory = subdir + "/releases" if subdir else "releases"
        requests.append((repo, branch or "HEAD", directory))
    owners = defaultdict(set)
    for (section, project), (default, entries) in zip(projects, read_trees(requests)):
        project = project.removesuffix("/tree/" + default)
        for e in entries:
            if e["type"] == "blob" and e["name"].lower().endswith(".rbf"):
                owners[section, e["oid"]].add(project)
    files = {}
    for path, digest in sorted(builds.items()):
        section = "arcade" if path.lower().startswith("_arcade/") else "system"
        choices = sorted(owners[section, blobs[path]])
        files[path] = [digest, choices]
        if len(choices) != 1 and files[path] != old.get("files", {}).get(path):
            log(f"::warning::Review official core {path}: " + (", ".join(choices) or "no matching project"))
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache_path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"signature": signature, "files": files}, indent=2) + "\n", encoding="utf-8")
    tmp.replace(cache_path)
    log(f"Official repository matches: {sum(len(v[1]) == 1 for v in files.values())}/{len(files)} builds.")
