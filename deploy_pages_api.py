# -*- coding: utf-8 -*-
"""GitHub Pages 部署兜底：git push 被墙时走 GitHub Contents API 直接更新 gh-pages。

用法: python deploy_pages_api.py [token]
token 缺省时从 git credential-manager 读取。
"""
import base64
import io
import json
import os
import subprocess
import sys
import urllib.request

REPO = "JivonKiang/etf-quant-auto"
BRANCH = "gh-pages"
LOCAL_FILE = os.path.join(os.path.dirname(__file__), "index.html")
REMOTE_PATH = "index.html"
API = "https://api.github.com"


def get_token():
    if len(sys.argv) > 1:
        return sys.argv[1]
    q = "protocol=https\nhost=github.com\n\n"
    p = subprocess.run(["git", "credential-manager", "get"], input=q,
                       capture_output=True, text=True)
    for line in p.stdout.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("NO TOKEN: pass as argv[1]")


def api(method, path, payload=None):
    req = urllib.request.Request(
        API + path, method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Authorization": "token " + TOKEN, "User-Agent": "deploy-agent",
                 "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
    except urllib.error.HTTPError as e:
        body = e.read()
        raise SystemExit(f"API {method} {path} -> HTTP {e.code}: {body.decode()[:300]}")
    return json.loads(body) if body else {}


def main():
    global TOKEN
    TOKEN = get_token()
    ref = api("GET", f"/repos/{REPO}/git/refs/heads/{BRANCH}")
    sha = ref["object"]["sha"]
    print("gh-pages HEAD:", sha)

    content = io.open(LOCAL_FILE, "rb").read()
    b64 = base64.b64encode(content).decode()
    print("payload size:", len(content), "bytes")

    res = api("PUT", f"/repos/{REPO}/contents/{REMOTE_PATH}", {
        "message": "deploy: SuperMind panel via contents API (git push blocked)",
        "content": b64,
        "branch": BRANCH,
        "sha": _file_sha(sha),
    })
    commit_sha = res.get("commit", {}).get("sha", "?")
    print("COMMIT OK:", commit_sha)
    return commit_sha


def _file_sha(branch_sha):
    """取 gh-pages 上 index.html 的 blob sha（PUT contents 需要）。"""
    res = api("GET", f"/repos/{REPO}/contents/{REMOTE_PATH}?ref={BRANCH}")
    return res["sha"]


if __name__ == "__main__":
    main()
