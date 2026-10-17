"""patch_urls.py - sort out which array is which, and (optionally) write a patched copy.

usage:
    python patch_urls.py <global-metadata.dat> <offset1> <offset2> [--base http://HOST:PORT]

offset1/offset2 are the two numbers from findurl2.py (6078176 and 6078344 for you).
Their order doesn't matter: the HIT test is symmetric, so findurl2.py could not say which
of the two is the 48-byte API url and which is the 56-byte OAuth url. This script decides it
by finding the 128-byte XOR key array itself in the file and checking which assignment
matches it.

Without --base it only analyses. With --base it writes global-metadata.patched.dat NEXT TO
the original (the original is never modified). Both urls keep their original byte length;
any spare room is filled with a harmless query string ("...?xxxx").

Printed: offsets, lengths and True/False checks. The key bytes are never printed.
"""
import argparse
import os
import sys

P1 = b"https://api.drama-prod.interactive-studio.jp/api"             # 48 bytes
P2 = b"https://api.drama-prod.interactive-studio.jp/oauth/token"     # 56 bytes
assert len(P1) == 48 and len(P2) == 56


def xor(a, b):
    return bytes(x ^ y for x, y in zip(a, b))


def fit(base, path, size):
    s = base.rstrip("/") + path
    if len(s) > size:
        sys.exit(f"--base is too long: '{s}' is {len(s)} bytes but the slot is {size}")
    if len(s) < size:
        s += "?" + "x" * (size - len(s) - 1)
    return s.encode()


ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("metadata")
ap.add_argument("offsets", nargs=2, type=int)
ap.add_argument("--base", help="local server base url, e.g. http://192.168.1.50:8080")
a = ap.parse_args()

data = open(a.metadata, "rb").read()
o1, o2 = a.offsets

cands = []
for api_off, oauth_off in ((o1, o2), (o2, o1)):
    ka = xor(data[api_off:api_off + 48], P1)
    ko = xor(data[oauth_off:oauth_off + 56], P2)
    if ka == ko[:48]:
        cands.append((api_off, oauth_off, ko))
print(f"assignments consistent with the known urls: {len(cands)} (expected 2: the test is symmetric)")
if not cands:
    sys.exit("neither assignment is consistent - wrong offsets or wrong file?")

prefix = cands[0][2][:44]
found, pos = [], data.find(prefix)
while pos != -1:
    found.append(pos)
    pos = data.find(prefix, pos + 1)
print(f"places where the first 44 key bytes occur: {found}")

chosen = None
for k in found:
    key = data[k:k + 128]
    for api_off, oauth_off, ko in cands:
        if len(key) == 128 and key[:56] == ko:
            chosen = (api_off, oauth_off, key, k)
if chosen is None:
    sys.exit("could not find the 128-byte key array, so the assignment is still undecided")

api_off, oauth_off, key, k = chosen
print(f"key array found at offset {k} (128 bytes)")
print(f"=> API url array   (48 bytes) at {api_off}")
print(f"=> OAuth url array (56 bytes) at {oauth_off}")
print(f"decrypting both with the key gives the known urls: "
      f"{xor(data[api_off:api_off+48], key[:48]) == P1 and xor(data[oauth_off:oauth_off+56], key[:56]) == P2}")

if not a.base:
    print("\nanalysis only. Add  --base http://HOST:PORT  to write a patched copy.")
    sys.exit(0)

new_api = fit(a.base, "/api", 48)
new_oauth = fit(a.base, "/oauth/token", 56)
out = bytearray(data)
out[api_off:api_off + 48] = xor(new_api, key[:48])
out[oauth_off:oauth_off + 56] = xor(new_oauth, key[:56])
assert len(out) == len(data)
assert xor(out[api_off:api_off + 48], key[:48]) == new_api
assert xor(out[oauth_off:oauth_off + 56], key[:56]) == new_oauth

dest = os.path.join(os.path.dirname(os.path.abspath(a.metadata)), "global-metadata.patched.dat")
if os.path.abspath(dest) == os.path.abspath(a.metadata):
    sys.exit("refusing to overwrite the input file")
with open(dest, "wb") as f:
    f.write(out)
print("\nwrote", dest)
print("  api   url ->", new_api.decode())
print("  oauth url ->", new_oauth.decode())
print("  file size unchanged:", len(out) == len(data))
