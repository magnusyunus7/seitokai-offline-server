A mitmproxy add-on that plays the game's dead server from your own recordings and files, so the game runs offline on an emulator.

This is a personal preservation project, not affiliated with the publisher. It contains no game files, and you need your own copy of the game and your own recordings. Do not publish or share game files, captures or save data.

###### Tested on: After School Sparkles, season 1 only (Seasons 2 to 4 were never captured) in LDPlayer 9. Actively testing on other games by the same studio.
---

## What it does

- Answers the game's two server hosts itself and never forwards those requests to the real server, so nothing you do reaches a real account.
  - API: `api.drama-prod.interactive-studio.jp` (`/oauth/token` and `/api`, MessagePack bodies)
  - CDN: `cdn.drama-prod.interactive-studio.jp/<package>/<uuid>`
- Learns the server's replies from every `*.flow` capture in its folder.
- Serves the game's files from a local data folder, by hash.
- Keeps progress, balances and purchases in `fake_state.json`.
- Blocks the ad network, so ad buttons show the game's own "no ads available" message instead of loading forever.
- Passes everything else (analytics, Google, and so on) through unchanged.

## What is emulated

| Area | Commands | Behaviour |
|---|---|---|
| Login | `/oauth/token` | Replays the recorded token reply |
| Profile | `050001` | Recorded reply, with `ticket`, `ruby`, `point` overridden from the config and adjusted by the state file |
| Cloud save | `050005`, `050004` | Saves are stored per slot; the game's position comes from the saved `data` blob |
| Chapter start | `050008` | Progress only moves forward. A chapter costs its listed tickets once, then replays are free |
| Premium choices | `080001`, `080002` | Price comes from the `080001` row; bought choices are remembered and flagged as owned |
| Exchange | `060004` | Points to rubies or tickets, tracked in the state file |
| Slot machine | `013001` | Point rewards are tracked in the state file |
| Language | `070001`, `070002` | Per-language text packs replayed from captures (English recorded) |
| File URLs | `020002` | Recorded URLs are reused; for unseen hashes, URLs pointing back at this server are invented |
| Ads | host block, `050018` | Ad hosts are blocked; the reward claim returns `False` |
| Anything else | | Replays the last recorded reply, or prints `UNKNOWN command` |

## Requirements

- Windows PC, LDPlayer 9 (rooted, ADB on) with the mitmproxy CA installed as a **system** certificate
- Python 3 in a virtual environment: `pip install -r requirements.txt`
- Run `mitmweb` from the venv. The standalone Windows mitmproxy build has its own bundled Python and cannot see packages installed in the venv.
- The Play Store build of the game, installed unmodified

## Folder layout (runtime)

The script finds its data relative to its own folder, so keep this layout. Items in **bold** are not in git.

```
new_version/
  captures/
    fake_server.py          the add-on
    fake_config.json        ticket / ruby / point overrides
    **fake_state.json**     created at runtime: saves, balances, purchases
    **<name>.flow**         your recordings (contain your login token)
    **old_flows/**          recordings kept but ignored
    **cdn_extra/**          CDN files recovered from recordings or the real CDN
  **snapshots/<snap>/external/data/<package>/**   game files pulled from a device
  **gamedata/external/data/<package>/**           optional older pull
```

If `data_dir` in the config is empty, the script picks the folder with the most files among `gamedata` and `snapshots`. After adding a second game or more snapshots, set `data_dir` explicitly.

## Daily use

1. Start the server, from `captures` with the venv active:
   ```powershell
   mitmweb --listen-port 8080 -s fake_server.py
   ```
2. Point the emulator at it (use your PC's address from `ipconfig`):
   ```powershell
   cd C:\LDPlayer\LDPlayer9
   .\adb.exe shell settings put global http_proxy <PC-IP>:8080
   ```
3. Open the game. If it asks for a language, pick English.
4. Turn the proxy off when you want normal internet back:
   ```powershell
   .\adb.exe shell settings put global http_proxy :0
   ```

On the first game request the terminal prints the data folder and file count (it should say 325 files for the season 1 snapshot) and the languages it learned.

### Restoring the game's data folder

Uninstalling the game, or using Android's **Clear storage** on it, deletes `/sdcard/Android/data/<package>/`. Push your snapshot back before the next launch:

```powershell
$s="<repo>\new_version\snapshots\<snap>\external"; $p="jp.interactive_studio.seitokai"
cd C:\LDPlayer\LDPlayer9
.\adb.exe push "$s\." /sdcard/Android/data/$p/files/
.\adb.exe shell "find /sdcard/Android/data/$p/files -type f | wc -l"
```

Taking a snapshot of a device is the same copy in the other direction (`adb pull`).

## Configuration

`fake_config.json`

```json
{
 "data_dir": "",
 "ticket": 99999,
 "ruby": 99999,
 "point": 99999
}
```

- `ticket`, `ruby`, `point`: starting balances. `null` means use whatever was recorded.
- `data_dir`: game files folder. Empty means auto-detect.
- Edits take effect after restarting mitmweb.

## State file

`fake_state.json` is written by the script. Do not edit it while mitmweb is running, because the next save overwrites your edit.

| Key | Meaning |
|---|---|
| `saves` | Per-slot cloud save: chapter, command, `data` blob, timestamps |
| `ruby_spent`, `ruby_earned` | Running totals |
| `point_spent`, `point_earned` | Running totals |
| `ticket_spent`, `ticket_earned` | Running totals |
| `bought` | Premium choices already purchased |
| `unlocked` | Chapters already charged (`episode:chapter`) |

Displayed balance = config value, minus spent, plus earned, never below 0.

To jump to a chapter: stop the server, set `chapter_id` in the save, and set `"chapterId":"ChN"` and `"commandId":null` inside the `data` string to match. Keep a backup first.

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| `No module named 'msgpack'` in mitmweb | mitmweb is not running from the venv. Run `pip install mitmproxy msgpack` inside the venv and start `mitmweb` from it |
| `Error while trying to access CDN server`, stuck loading | A file is missing. Check the terminal for `cdn MISSING` and see below |
| `cdn MISSING ... -> real CDN, will cache` then `cached` | Working as designed: the file was fetched once from the real CDN and stored in `cdn_extra` |
| `cdn MISSING` and no `cached` line | The real CDN refused it (check the status line). Record that file from a real session |
| `UNKNOWN command XXXXXX` | A reply you have not recorded. Record a session through the real server, or find the response shape in the il2cpp dump |
| Game returns to chapter 1 after closing | The saved chapter was overwritten. `050008` must only move progress forward, and `chapter_id` in the save must match the `data` blob |
| Ad button loops forever | The ad hosts are not being blocked. Restart mitmweb and the game |
| Game restarts at the language screen | Normal after clearing the app's data. Pick the same language |

## Recording what is missing

Everything the fake server knows came from real sessions recorded while the real server was still up. To fill a gap:

1. In a clone of the emulator with the game's data cleared, run `mitmweb --listen-port 8080 -w <name>.flow` (without the script).
2. Play the part that is missing. Let every download finish.
3. Stop mitmweb with Ctrl+C so the file saves. Move it into `captures`.

A first-launch recording is needed for the language screen and the initial downloads. The game's "restart story" option makes it download the early chapters again.

## Known limits

- The server is not fully offline until the real-CDN fallback is turned off. It currently fetches any file it lacks, once, then caches it. A flag to disable it would show gaps as plain 404s.
- **No patched APK.** The game checks that it was installed from Google Play. A re-signed, unmodified rebuild already refuses to start ("get it on Google Play"), so redirecting the app to another server by repackaging it does not work. Do not expect a standalone APK from this project.
- Phone play needs a rooted phone, with the mitmproxy CA as a system certificate and the two game hostnames redirected to the server. This has not been tested.

## Reverse-engineering notes (this build)

- Engine: Unity IL2CPP, arm64 only. The base APK holds `global-metadata.dat`; the split APK holds `libil2cpp.so`. Tools: Il2CppDumper, Ghidra with the dumper's script.
- Network code: the API client is `FPPOOLFBDBH`, built by `IFCJFFGGLME`. The URL comes from `BPODNMBNGML`, which keeps its strings as encrypted byte arrays and decrypts them with a repeating-key XOR (key array of 128 bytes, in the same file).
- In `global-metadata.dat` of this build: key array at offset 6057576, API URL array at 6078176 (48 bytes), OAuth URL array at 6078344 (56 bytes).
- API: MessagePack. A request is a list of command objects (`{"id": "050001", ...}`) and the reply is a dict keyed by command ID.
- Game catalog: `drama.dat` (a header, then a raw deflate stream from byte 31) lists file hashes in chapter order. The first 8 entries are shared files. It lists 376 hashes, and the server's `020002` list covers about 1,121.
- Ads: LevelPlay (ironSource) through Unity mediation.

## Doing this for another game from the same studio

The studio's games appear to share a framework, so expect the same API shape. Not verified.

1. Move the package name, hosts and paths into the config instead of constants at the top of the script.
2. Use a separate folder per game (captures, snapshots, state).
3. Record a clean first launch through the real server first, then play everything with the proxy on, so CDN bodies end up in the flows.
4. Check the commands in the first captures against this table. Expect per-game differences in the catalog, the chapter list, the save blob and any game-specific features.

## Do not commit

Keep these out of git. Recordings contain your login token and account ID, and the game files belong to the publisher.

```
*.flow
fake_state.json
cdn_extra/
old_flows/
snapshots/
gamedata/
*.apk
*.so
*.dat
```
