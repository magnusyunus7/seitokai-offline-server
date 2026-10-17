"""mitmproxy addon: saves the game's API bodies and logs its CDN downloads.

Put this file in the same folder as your .flow captures, then run:

    mitmdump -nr session.flow -s dump_api.py --set flow_detail=0

(-n = don't start a proxy, -r = read the saved flow file,
 flow_detail=0 = hide mitmproxy's own per-request lines, so only ours print)

* API calls (api.drama-prod...) are numbered, printed, and their request and
  response bodies saved to  api_bodies/<name of the .flow file>/
* CDN downloads (cdn.drama-prod...) are only printed (path, status, size) and
  NOT saved, so chapter files don't get copied twice.

Printed lines contain no headers or bodies. The saved .bin files DO contain your
account data - keep them out of git.
"""
import os
from urllib.parse import parse_qsl, urlsplit

from mitmproxy import ctx, http

API_HOST = "api.drama-prod.interactive-studio.jp"
CDN_HOST = "cdn.drama-prod.interactive-studio.jp"
BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "api_bodies")
_out = None
count = 0


def out_dir():
    global _out
    if _out is None:
        src = getattr(ctx.options, "rfile", None) or "live"
        _out = os.path.join(BASE, os.path.splitext(os.path.basename(src))[0])
        os.makedirs(_out, exist_ok=True)
    return _out


def response(flow: http.HTTPFlow):
    global count
    host = flow.request.pretty_host
    if host not in (API_HOST, CDN_HOST) or flow.response is None:
        return
    u = urlsplit(flow.request.pretty_url)
    qkeys = ",".join(k for k, _ in parse_qsl(u.query))
    res = flow.response.content or b""      # .content = transport-decompressed body
    line = (f"{flow.request.method} {host}{u.path}"
            + (f"?{qkeys}=..." if qkeys else "")
            + f" status={flow.response.status_code}"
            + f" rtype={flow.response.headers.get('content-type')}"
            + f" resp={len(res)}B http={flow.request.http_version}")
    if host == CDN_HOST:
        print("CDN " + line)
        return
    count += 1
    req = flow.request.content or b""
    stem = f"{count:03d}_{flow.request.method}"
    with open(os.path.join(out_dir(), stem + "_req.bin"), "wb") as f:
        f.write(req)
    with open(os.path.join(out_dir(), stem + "_resp.bin"), "wb") as f:
        f.write(res)
    print(f"{count:03d} {line} ctype={flow.request.headers.get('content-type')} req={len(req)}B")