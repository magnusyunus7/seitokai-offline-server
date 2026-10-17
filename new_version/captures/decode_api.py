"""Prints the SHAPE of each saved API body (field names + value types only).

Values are never printed, so the output is safe to paste.
Requires:  pip install msgpack
Run from anywhere:  python decode_api.py
Looks in ./api_bodies next to this file.
"""
import glob
import gzip
import json
import os
import zlib

import msgpack

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "api_bodies")


def tree(o, depth=0):
    if depth > 5:
        return "..."
    if isinstance(o, dict):
        return {str(k): tree(v, depth + 1) for k, v in list(o.items())[:60]}
    if isinstance(o, (list, tuple)):
        first = json.dumps(tree(o[0], depth + 1)) if o else "empty"
        return f"list[{len(o)}] of {first}"
    if isinstance(o, bytes):
        return f"bytes({len(o)})"
    if isinstance(o, str):
        return f"str({len(o)})"
    return type(o).__name__


def try_decode(data):
    # plain msgpack first, then msgpack inside zlib/gzip
    for label, fn in (("msgpack", lambda x: x),
                      ("zlib+msgpack", zlib.decompress),
                      ("gzip+msgpack", gzip.decompress)):
        try:
            return label, msgpack.unpackb(fn(data), raw=False, strict_map_key=False)
        except Exception:
            continue
    return None, None


files = sorted(glob.glob(os.path.join(D, "*.bin")))
if not files:
    print("No .bin files found in", D)
for path in files:
    data = open(path, "rb").read()
    label, obj = try_decode(data)
    print("=" * 70)
    print(os.path.basename(path), f"({len(data)} bytes)")
    if obj is None:
        print("not msgpack. first 16 bytes (hex):", data[:16].hex())
    else:
        print("decoded as", label)
        print(json.dumps(tree(obj), indent=1)[:3500])
