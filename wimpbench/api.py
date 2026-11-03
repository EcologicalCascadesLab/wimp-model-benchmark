"""Minimal WIMP (Agouti) API client.

Keys come from the environment only: WIMP_PROD_KEY, WIMP_TEST_KEY.
An API key (pk_...) is sent as X-API-KEY; anything else as a Bearer token.
The key is never printed or written to disk by this module.
"""
import io
import os
import sys
import time

import pandas as pd
import requests

BASES = {
    "prod": "https://api.wimp.wildobs.org.au/v1",
    "test": "https://api.wimp.test.wildobs.org.au/v1",
}


class Api:
    def __init__(self, env):
        if env not in BASES:
            raise ValueError(f"env must be one of {list(BASES)}")
        var = f"WIMP_{env.upper()}_KEY"
        key = (os.environ.get(var) or "").strip()
        if not key:
            sys.exit(f"KEY: set {var} (WIMP > User settings > API keys)")
        if key.lower().startswith("bearer "):
            key = key[7:].strip()
        self.env, self.base = env, BASES[env]
        self.headers = {"X-API-KEY": key} if key.startswith("pk_") else {"Authorization": "Bearer " + key}
        self.session = requests.Session()

    def call(self, method, path, tries=4, timeout=120, **kw):
        last = None
        url = path if path.startswith("http") else self.base + path
        for i in range(tries):
            try:
                r = self.session.request(method, url, headers=self.headers, timeout=timeout, **kw)
            except requests.RequestException as e:
                last = str(e)
                time.sleep(3 * (i + 1))
                continue
            if r.status_code == 401:
                sys.exit(f"AUTH: {self.env} key rejected or expired (401)")
            if r.status_code >= 500 and i < tries - 1:
                last = f"{r.status_code} {r.text[:200]}"
                time.sleep(3 * (i + 1))
                continue
            return r
        raise RuntimeError(f"{method} {path} failed: {last}")

    def get(self, path, **kw):
        r = self.call("GET", path, **kw)
        if r.status_code != 200:
            raise RuntimeError(f"GET {path}: {r.status_code} {r.text[:300]}")
        return r.json()

    def csv(self, path, **params):
        r = self.call("GET", path, params=params or None, timeout=600)
        if r.status_code != 200:
            raise RuntimeError(f"GET {path}: {r.status_code} {r.text[:300]}")
        return pd.read_csv(io.StringIO(r.text), dtype=str)

    def projects(self):
        return self.get("/me/projects")

    def find_project(self, fragment):
        hits = [p for p in self.projects() if fragment.lower() in p["name"].lower() or p["id"] == fragment]
        return hits
