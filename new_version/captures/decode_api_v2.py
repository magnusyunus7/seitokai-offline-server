"""Prints the SHAPE of each saved API body, plus a few non-identifying details.

Compared with v1 it also shows:
  * every command id in a request (the 6-digit codes like 050001)
  * values of an allow-list of harmless fields (ids, counts, ticket/ruby, timers)
  * URLs reduced to host + path layout (long tokens/hashes masked, query values removed)

It never prints: email, identifier, account_id, tokens, hashes, keys, passwords.
Requires:  pip install msgpack
Run:       python decode_api_v2.py [folder]   (default: ./api_bodies next to this file;
           for a newer capture pass its folder, e.g. api_bodies\\session_2
"""
import glob
import gzip
import json
import os
import re
import sys
import zlib
from urllib.parse import parse_qsl, urlsplit

import msgpack

D = (os.path.abspath(sys.argv[1]) if len(sys.argv) > 1
     else os.path.join(os.path.dirname(os.path.abspath(__file__)), "api_bodies"))

SAFE = {
    "id", "app_type_id", "language_id", "drama_id", "episode_id", "chapter_id",
    "save_slot", "story_id", "episode_type", "chapter_num", "order", "tickets",
    "ticket", "ruby", "point", "lang", "serial", "weight", "asset_id",
    "asset_group_id", "asset_num", "ex_asset_group_id", "ex_asset_num", "iso",
    "ai_translation", "isNewUser", "isPayingUser", "badge", "is_available",
    "available_at", "bonus", "free_ticket_time_stamp", "video_bonus_time_stamp",
    "is_init", "title", "game", "adnetwork",
}
SAFE_FORM = {"grant_type"}


def url_shape(s):
    u = urlsplit(s)
    parts = []
    for seg in u.path.split("/"):
        if re.fullmatch(r"[0-9a-fA-F]{16,}", seg):
            parts.append(f"<hex{len(seg)}>")
        elif len(seg) > 20:
            parts.append(f"<{len(seg)}chars>")
        else:
            parts.append(seg)
    q = ",".join(k for k, _ in parse_qsl(u.query))
    return f"{u.scheme}://{u.netloc}{'/'.join(parts)}" + (f"?{q}=..." if q else "")


def tree(o, depth=0):
    if depth > 5:
        return "..."
    if isinstance(o, dict):
        out = {}
        for k, v in list(o.items())[:60]:
            k = str(k)
            if k in SAFE and isinstance(v, (bool, int, float)):
                out[k] = v
            elif k in SAFE and isinstance(v, str) and len(v) < 40:
                out[k] = v
            else:
                out[k] = tree(v, depth + 1)
        return out
    if isinstance(o, (list, tuple)):
        if not o:
            return "empty list"
        if all(isinstance(x, dict) for x in o) and all("id" in x for x in o):
            return {"_count": len(o),
                    "_ids": [str(x["id"]) for x in o][:40],
                    "_first": tree(o[0], depth + 1)}
        if all(isinstance(x, (list, tuple)) and x and
               all(isinstance(y, int) for y in x) for x in o[:3]):
            return f"list[{len(o)}] of int-rows, first rows: {[list(r) for r in o[:2]]}"
        return {"_count": len(o), "_first": tree(o[0], depth + 1)}
    if isinstance(o, bytes):
        return f"bytes({len(o)})"
    if isinstance(o, str):
        return "url: " + url_shape(o) if o.startswith("http") else f"str({len(o)})"
    return type(o).__name__


def try_msgpack(data):
    for label, fn in (("msgpack", lambda x: x),
                      ("zlib+msgpack", zlib.decompress),
                      ("gzip+msgpack", gzip.decompress)):
        try:
            return label, msgpack.unpackb(fn(data), raw=False, strict_map_key=False)
        except Exception:
            continue
    return None, None


def describe_plain(data):
    txt = data.decode("utf-8", "replace")
    try:
        return "json:\n" + json.dumps(tree(json.loads(txt)), indent=1)
    except Exception:
        pass
    if "=" in txt and not txt.lstrip().startswith(("{", "[")):
        pairs = [p.split("=", 1) for p in txt.split("&") if "=" in p]
        shown = [f"{k}={v}" if k in SAFE_FORM else f"{k}=<{len(v)} chars>" for k, v in pairs]
        return "form fields: " + ", ".join(shown)
    return "unknown text; first 16 bytes (hex): " + data[:16].hex()


files = sorted(glob.glob(os.path.join(D, "*.bin")))
if not files:
    print("No .bin files found in", D)
for path in files:
    data = open(path, "rb").read()
    print("=" * 70)
    print(os.path.basename(path), f"({len(data)} bytes)")
    label, obj = try_msgpack(data)
    if obj is None:
        print(describe_plain(data)[:3500])
    else:
        print("decoded as", label)
        print(json.dumps(tree(obj), indent=1, default=str)[:4500])