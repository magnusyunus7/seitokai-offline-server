"""fake_server.py - plays the game's server from YOUR OWN captures and files.

Run it instead of plain mitmweb (same proxy setup as before):

    mitmweb --listen-port 8080 -s fake_server.py

Put this file in your `captures` folder. What it does:

  * learns the server's replies from every *.flow capture in this folder
  * answers  api.drama-prod.interactive-studio.jp/oauth/token  and  /api  itself,
    WITHOUT forwarding them to the real server (so nothing you do reaches the real
    account: tickets, saves and chapter starts all stay local)
  * answers  cdn.drama-prod.interactive-studio.jp/<package>/<uuid>  from the
    hash-named files in your data folder; unknown hashes get a 404
  * lets every other request (ads, Google, Facebook, the CDN's ad images) pass through

Edit fake_config.json (created on first run) to hard-code ticket / ruby / point.
Progress is kept in fake_state.json.  Both stay on your PC - keep them out of git,
because the captures it reads contain your login token and account id.
"""
import datetime
import glob
import json
import os
import uuid

import msgpack
from mitmproxy import http, io
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
API_HOST = "api.drama-prod.interactive-studio.jp"
CDN_HOST = "cdn.drama-prod.interactive-studio.jp"
AD_HOSTS = ("mediation.unity3d.com", "unityads.unity3d.com", "offerwall.unity3d.com",
            "unity3dusercontent.com", "supersonicads.com", "ironsrc.com")


def _read_pkg():
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fake_config.json"),
                  encoding="utf-8-sig") as f:
            p = json.load(f).get("package")
        if p:
            return p
    except Exception:
        pass
    return "jp.interactive_studio.seitokai"        # default: season 1


PKG = _read_pkg()
EXTRA_DIR = os.path.join(HERE, "cdn_extra")   # CDN files recovered from your .flow captures
CONFIG_PATH = os.path.join(HERE, "fake_config.json")
STATE_PATH = os.path.join(HERE, "fake_state.json")
DEFAULT_CONFIG = {
    "data_dir": "",      # folder holding the hash-named files; empty = auto-detect
    "ticket": None,      # a number here is returned on every profile reply
    "ruby": None,
    "point": None,
}

cfg = {}
state = {"saves": {}}
replies = {}             # command id -> latest recorded reply value
by_shape = {}            # (n commands, sorted ids) -> latest recorded full reply dict
lang_replies = {}        # language_id -> recorded 070002 reply
token_body = None
token_ctype = "application/json; charset=UTF-8"
urls_by_hash = {}        # file hash -> list of CDN urls (as recorded)
uuid_to_hash = {}
data_dir = None
_loaded = False
_seen_unknown = set()


def _uuid(path):
    return path.split("?")[0].rstrip("/").rsplit("/", 1)[-1]


def _load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_state():
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1)


def _bal(res, delta):                    # delta < 0 = spent, delta > 0 = earned
    k = f"{res}_{'earned' if delta > 0 else 'spent'}"
    state[k] = state.get(k, 0) + abs(delta)


def _unpack(b):
    return msgpack.unpackb(b, raw=False, strict_map_key=False)


def _shape(cmds):
    return (len(cmds), tuple(sorted(str(c.get("id")) for c in cmds if isinstance(c, dict))))


def _pick_data_dir():
    if cfg.get("data_dir"):
        return cfg["data_dir"]
    cands = glob.glob(os.path.join(HERE, "..", "gamedata", "external", "data", PKG))
    cands += glob.glob(os.path.join(HERE, "..", "snapshots", "*", "external", "data", PKG))
    cands = [c for c in cands if os.path.isdir(c)]
    return max(cands, key=lambda d: len(os.listdir(d))) if cands else None


def _register_urls(h, urls):
    urls_by_hash[h] = urls
    for u in urls:
        if isinstance(u, str):
            uuid_to_hash[u.rstrip("/").rsplit("/", 1)[-1]] = h


def _map_urls(o):                        # url + hash pairs outside 020002 (e.g. manifest_list)
    if isinstance(o, dict):
        u, h = o.get("url"), o.get("hash")
        if isinstance(u, str) and isinstance(h, str) and CDN_HOST in u:
            uuid_to_hash[u.rstrip("/").rsplit("/", 1)[-1]] = h
        for v in o.values():
            _map_urls(v)
    elif isinstance(o, list):
        for v in o:
            _map_urls(v)


def _learn(path):
    global token_body, token_ctype
    n = 0
    with open(path, "rb") as f:
        for fl in io.FlowReader(f).stream():
            if not isinstance(fl, http.HTTPFlow) or fl.response is None:
                continue
            if fl.request.pretty_host == CDN_HOST:        # keep real CDN bodies from the flows
                if fl.response.status_code == 200 and fl.request.path.startswith(f"/{PKG}/"):
                    fp = os.path.join(EXTRA_DIR, _uuid(fl.request.path))
                    if not os.path.exists(fp):
                        os.makedirs(EXTRA_DIR, exist_ok=True)
                        with open(fp, "wb") as out:
                            out.write(fl.response.content)
                continue
            if fl.request.pretty_host != API_HOST:
                continue
            if fl.request.path.startswith("/oauth/token"):
                token_body = fl.response.content
                token_ctype = fl.response.headers.get("content-type", token_ctype)
            elif fl.request.path.startswith("/api"):
                try:
                    cmds, resp = _unpack(fl.request.content), _unpack(fl.response.content)
                except Exception:
                    continue
                if not isinstance(cmds, list) or not isinstance(resp, dict):
                    continue
                n += 1
                by_shape[_shape(cmds)] = resp
                replies.update(resp)
                _map_urls(resp)
                for c in cmds:           # file-URL lookups: hash list in, URL lists out
                    if isinstance(c, dict) and c.get("id") == "020002" and "020002" in resp:
                        hl, ul = c.get("hash_list", []), resp["020002"]
                        for h, urls in zip(hl, ul):
                            if h not in urls_by_hash:
                                print("[fake] 020002 sample:", h[:8], repr(urls)[:300])
                            _register_urls(h, urls)
                    if isinstance(c, dict) and c.get("id") == "070002" and "070002" in resp:
                        lang_replies[str(c.get("language_id"))] = resp["070002"]
    return n


def _ensure_loaded():
    global cfg, state, data_dir, _loaded
    if _loaded:
        return
    _loaded = True
    cfg = _load_json(CONFIG_PATH, None)
    if cfg is None:
        cfg = dict(DEFAULT_CONFIG)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=1)
        print(f"[fake] created {CONFIG_PATH}")
    for k, v in DEFAULT_CONFIG.items():
        cfg.setdefault(k, v)
    state = _load_json(STATE_PATH, {"saves": {}})
    total = 0
    for p in sorted(glob.glob(os.path.join(HERE, "*.flow")), key=os.path.getmtime):   # oldest first
        total += _learn(p)
    data_dir = _pick_data_dir()
    nfiles = len(os.listdir(data_dir)) if data_dir else 0
    print(f"[fake] learned {total} api calls, {len(replies)} command ids, "
          f"{len(urls_by_hash)} hashes with urls, token={'yes' if token_body else 'NO'}")
    print(f"[fake] data dir: {data_dir} ({nfiles} files)")
    if not token_body or "050001" not in replies:
        print("[fake] WARNING: no login/profile found - capture a normal boot into a .flow file here first")
    # print("[fake] 070001 =", repr(replies.get("070001"))[:600])
    # print("[fake] 070002 languages:", sorted(lang_replies))
    print("[fake] manifest_list =", repr((replies.get("020001") or {}).get("manifest_list"))[:500])

def _profile():
    p = dict(replies.get("050001") or {})
    for k in ("ticket", "ruby", "point"):
        if cfg.get(k) is not None:
            p[k] = cfg[k]
    for k in ("ruby", "point", "ticket"):
        if isinstance(p.get(k), int):
            p[k] = max(0, p[k] - state.get(f"{k}_spent", 0) + state.get(f"{k}_earned", 0))
    return p


def _toint(v):
    return int(v) if isinstance(v, str) and v.lstrip("-").isdigit() else v


def _save_record(slot):
    rec = state["saves"].get(str(slot))
    if rec is None:
        rec = dict((replies.get("050005") or [{}])[0])
    return rec


def _answer(cid, c):
    if cid in ("050004", "050005", "050008"):
        print(f"[fake] {cid} req { {k: (str(v)[:70] if k == 'data' else v) for k, v in c.items() if k != 'id'} }")
    if cid == "020002":                  # urls for a list of file hashes
        out = []
        for h in c.get("hash_list", []):
            if h not in urls_by_hash:    # unseen hash: invent urls we can serve ourselves
                u = str(uuid.uuid5(uuid.NAMESPACE_URL, h))
                _register_urls(h, [f"https://{CDN_HOST}/{PKG}/{u}"] * 5)
            out.append(urls_by_hash[h])
        return out
    if cid == "050001":
        return _profile()
    if cid == "050004":                  # save upload
        slot = str(_toint(c.get("save_slot", 1)))
        rec = _save_record(slot) or {}
        for k in ("drama_id", "episode_id", "story_id", "chapter_id", "command_id",
                  "save_slot", "point"):
            if k in c:
                rec[k] = _toint(c[k])
        if "data" in c:
            rec["data"] = c["data"]
        rec["last_played_at"] = datetime.datetime.now(ZoneInfo("Asia/Singapore")).strftime("%Y-%m-%d %H:%M:%S")
        state["saves"][slot] = rec
        _save_state()
        return []
    if cid == "050005":                  # cloud save
        rec = _save_record(c.get("save_slot", 1))
        print(f"[fake] 050005 reply { {k: (str(v)[:90] if k == 'data' else v) for k, v in (rec or {}).items()} }")
        return [rec] if rec else []
    if cid == "050006":                  # restart story; the game uploads a fresh ch1 save (050004) right after
        print(f"[fake] restart story, slot {c.get('save_slot', 1)}")
        return []
    if cid == "050008":                  # start / unlock a chapter
        slot = str(_toint(c.get("save_slot", 1)))
        ep, ch = _toint(c.get("episode_id")), _toint(c.get("chapter_id"))
        rec = _save_record(slot)
        if rec:
            if (ep or 0, ch or 0) > (rec.get("episode_id") or 0, rec.get("chapter_id") or 0):
                rec["episode_id"], rec["chapter_id"] = ep, ch    # only advance, never go back
            state["saves"][slot] = rec
        key = f"{ep}:{ch}"
        unlocked = state.setdefault("unlocked", [])
        if key not in unlocked:          # charge once per chapter, never on replays
            row = next((r for r in (replies.get("020001") or {}).get("chapter_list", [])
                        if r.get("episode_id") == ep and r.get("order") == ch), None)
            cost = row["tickets"] if row else 0
            unlocked.append(key)
            if cost:
                _bal("ticket", -cost)
            print(f"[fake] chapter {key} unlocked, cost {cost} ticket(s)")
        _save_state()
        return []
    if cid == "050018":                  # ad reward claim: reply is a bool (+ profile); False = nothing granted
        return False
    if cid == "060004":                  # exchange points: asset 11 = rubies, 12 = tickets
        asset = _toint(c.get("asset_id"))
        got, cost = _toint(c.get("asset_num", 0)), _toint(c.get("exchange_asset_num", 0))
        res = {11: "ruby", 12: "ticket"}.get(asset)
        if res and isinstance(got, int) and isinstance(cost, int):
            _bal(res, got)
            _bal("point", -cost)
            _save_state()
        else:
            print(f"[fake] exchange not handled yet: { {k: v for k, v in c.items() if k != 'id'} }")
        return []
    if cid == "070002":                  # i18n pack for the chosen language
        lang = str(c.get("language_id", 1))
        return lang_replies.get(lang) or lang_replies.get("1") or {}
    if cid == "080001":                  # premium list: flag bought products
        bought = set(state.get("bought", []))
        idx = cfg.get("purchased_idx", 8)
        out = []
        for r in replies.get("080001") or []:
            r = list(r)
            if len(r) > idx and r[1] in bought:
                r[idx] = 1
            out.append(r)
        return out
    if cid == "080002":                  # premium choice bought with rubies
        key = c.get("product_key")
        row = next((r for r in (replies.get("080001") or []) if len(r) > 6 and r[1] == key), None)
        price = row[6] if row else (cfg.get("premium_price") or 0)
        bought = state.setdefault("bought", [])
        if key not in bought:            # charge once per product, never on retries
            bought.append(key)
            _bal("ruby", -price)
            _save_state()
        print(f"[fake] ruby purchase {key} cost {price}")
        return []
    if cid == "011002":                  # seen in season 1: a list with one 8-character string
        return replies.get("011002") or ["00000000"]
    if cid == "013001":                  # slot spin: replay the recorded result, credit its points
        r = dict(replies.get("013001") or {})
        if isinstance(r.get("point"), int) and r["point"] > 0:
            _bal("point", r["point"])
            _save_state()
        return r
    if cid in replies:
        return replies[cid]
    if cid not in _seen_unknown:         # print each unknown command once
        _seen_unknown.add(cid)
        shown = {k: v for k, v in c.items()
                 if k not in ("id", "account_id", "identifier", "email", "token") and len(str(v)) < 60}
        print(f"[fake] UNKNOWN command {cid} {shown} -> []")
    return []


def _api(flow):
    cmds = _unpack(flow.request.content)
    out = dict(by_shape.get(_shape(cmds), {}))   # identical past request: start from its reply
    for c in cmds:
        if isinstance(c, dict) and "id" in c:
            out[c["id"]] = _answer(c["id"], c)
    ids = [c.get("id") for c in cmds if isinstance(c, dict)]
    print(f"[fake] api  {' '.join(str(i) for i in ids)}")
    flow.response = http.Response.make(
        200, msgpack.packb(out, use_bin_type=True), {"Content-Type": "application/x-msgpack"})


def _cdn(flow):
    u = _uuid(flow.request.path)
    h = uuid_to_hash.get(u)
    cands = ([os.path.join(data_dir, h)] if (h and data_dir) else []) + [os.path.join(EXTRA_DIR, u)]
    fp = next((p for p in cands if os.path.isfile(p)), None)
    if fp:
        with open(fp, "rb") as f:
            body = f.read()
        print(f"[fake] cdn  served {os.path.basename(fp)[:8]}.. ({len(body)} bytes)")
        flow.response = http.Response.make(200, body, {"Content-Type": "application/octet-stream"})
    else:
        print(f"[fake] cdn  MISSING {h or 'unknown-uuid'} {flow.request.path} -> real CDN, will cache")
        flow.metadata["passthrough"] = True      # no response set, so mitmproxy forwards it


def request(flow: http.HTTPFlow):
    host = flow.request.pretty_host
    if host.endswith(AD_HOSTS):          # no ad fill -> the game shows "no ads available"
        print(f"[fake] ad blocked {host}")
        flow.kill()
        return
    if host == API_HOST:
        _ensure_loaded()
        if flow.request.path.startswith("/oauth/token"):
            print("[fake] login -> recorded token")
            flow.response = http.Response.make(200, token_body or b"{}", {"Content-Type": token_ctype})
        elif flow.request.path.startswith("/api"):
            _api(flow)
    elif host == CDN_HOST and flow.request.path.startswith(f"/{PKG}/"):
        _ensure_loaded()
        _cdn(flow)


def response(flow: http.HTTPFlow):
    if (flow.metadata.get("passthrough") and flow.response
            and flow.response.status_code == 200 and flow.response.content):
        fp = os.path.join(EXTRA_DIR, _uuid(flow.request.path))
        if not os.path.exists(fp):
            os.makedirs(EXTRA_DIR, exist_ok=True)
            with open(fp, "wb") as f:
                f.write(flow.response.content)
            print(f"[fake] cdn  cached {_uuid(flow.request.path)[:8]}.. ({len(flow.response.content)} bytes)")
