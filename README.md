# Interactive Studio Inc. games offline server

A mitmproxy add-on that plays Interactive Studio Inc. games from your own recordings and files, so the game runs offline on an emulator.

This is a personal preservation project, not affiliated with the publisher. It contains no game files. You need your own copy of the game and your own recordings. Do not publish or share game files, recordings or save data.

###### Actively testing all the games, further generalization will be implemented if needed

## What it does

- Answers the game's API host itself and never forwards those requests to the real server, so nothing you do reaches a real account.
  - API: `api.drama-prod.interactive-studio.jp` (`/oauth/token` and `/api`, MessagePack bodies)
  - CDN: `cdn.drama-prod.interactive-studio.jp/<package>/<uuid>`
- Learns the server's replies from every `*.flow` recording in its folder, including the CDN file bodies inside them.
- Serves the game's files from local folders, by hash. If a file is missing, it can fetch it once from the real CDN and keep it (see **The real-CDN fallback**).
- Keeps progress, balances and purchases in `fake_state.json`.
- Blocks the ad network, so ad buttons show the game's own "no ads available" message instead of loading forever.
- Passes everything else (analytics, Google, and so on) through unchanged.

## Requirements

- Windows PC, LDPlayer 9 (rooted, ADB on) with the mitmproxy CA installed as a **system** certificate
- Python 3 in a virtual environment: `pip install -r requirements.txt`
- Run `mitmweb` from the venv. The standalone Windows mitmproxy build has its own bundled Python and cannot see packages installed in the venv.
- The Play Store build of the game, installed unmodified

## Known limits

- **The fallback is always on.** The server fetches any file it lacks from the real CDN when it can, so a run that works today may be using the real CDN without you noticing. Each `cdn MISSING ... -> real CDN` line in the terminal is a file that is not stored locally yet.
- The fallback stops working when the CDN is shut down. Only files you already downloaded or cached are available after that.
- **No patched APK.** The game checks that it was installed from Google Play. A re-signed, unmodified rebuild already refuses to start ("get it on Google Play"), so redirecting the app to another server by repackaging it does not work. Do not expect a standalone APK from this project.
- Phone play needs a rooted phone, with the mitmproxy CA as a system certificate and the two game hostnames redirected to the server. This has not been tested.

## Folder layout (runtime)

The script finds its data relative to its own folder, so keep this layout. Items in ****bold**** are not in git.

```
new_version/
  captures/
    fake_server.py          the add-on
    fake_config.json        package, balances, data folder
    **fake_state.json**     created at runtime: saves, balances, purchases
    **<name>.flow**         your recordings (contain your login token)
    **old_flows/**          recordings kept but ignored
    **cdn_extra/**          CDN files recovered from recordings or the real CDN
  **snapshots/<snap>/external/data/<package>/**   game files pulled from a device
  **gamedata/external/data/<package>/**           optional older pull
```

If `data_dir` in the config is empty, the script picks the folder with the most files among `gamedata` and `snapshots`. With more than one game or snapshot, set `data_dir` explicitly.

## Finding a game's package name

The server needs the game's package name (for example `jp.interactive_studio.<name>`). It sets the `package` key in `fake_config.json`, the CDN path, and the data folder on the device. Any one of these finds it:

1. **List the installed games** on the emulator. Install the game first, then run this from the LDPlayer folder (add `-s <serial>` after `adb.exe` if several instances are running; get the serial from `.\adb.exe devices`):
   ```powershell
   .\adb.exe shell pm list packages -3 | Select-String interactive_studio
   ```
2. **Ask the running game.** Open the game and keep it in the foreground, then run:
   ```powershell
   .\adb.exe shell dumpsys window | Select-String mCurrentFocus
   ```
   The package is the part before the `/` in the output.
3. **Read it from the Play Store link.** In the game's Play Store web address, the package is the text after `id=`.
4. **Read it from the traffic.** CDN requests look like `cdn.drama-prod.interactive-studio.jp/<package>/<uuid>`, so the first path segment in the mitmweb flow list is the package.
5. **Read it from the device's data folder.** The game's files live under a folder with the package name:
   ```powershell
   .\adb.exe shell ls /sdcard/Android/data
   ```

Then set it in the config, and set `data_dir` to the matching snapshot folder:

```json
{ "package": "jp.interactive_studio.<name>" }
```

## Before you start: record a first launch (required)

The server answers the game's API only from your own recordings. Without a recording of a real first launch, the game cannot log in or get its profile, chapter list or file URLs, so this step cannot be skipped. You need it once per game, and it has to be done while the real server is still up.

1. Install the game on the emulator and set up the proxy (see **Requirements**).
2. In the `captures` folder, start a plain recording, without the add-on:
```powershell
   mitmweb --listen-port 8080 -w <name>.flow
```
3. Open the game and pick a language. Let every initial download finish, then play into the first chapter. If the account has already progressed, use the game's **restart story** option, which makes it download the early chapters again.
4. Close the game, then press Ctrl+C in the terminal so the file saves.
5. Pull the game's data folder from the device (`adb pull`) into `snapshots/`, so the downloaded files are also kept locally.
6. Set `package` in `fake_config.json` and start the server (see **Daily use**).

The recording contains your login token and account ID, so keep it private and never share it. After this, files you have not downloaded yet can be filled in by the CDN fallback while the real CDN is up.

## Configuration

`fake_config.json`

```json
{
 "data_dir": "",
 "ticket": 99999,
 "ruby": 99999,
 "point": 99999,
 "package": "jp.interactive_studio.<name>"
}
```

- `data_dir`: game files folder. Empty means auto-detect.
- `ticket`, `ruby`, `point`: starting balances. `null` means use whatever was recorded.
- `package`: the game's package name. Defaults to `jp.interactive_studio.seitokai` if missing.
- Edits take effect after restarting mitmweb.

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

On the first game request the terminal prints the data folder and its file count (check it matches your snapshot) and the languages it learned.

### Restoring the game's data folder

Uninstalling the game, or using Android's **Clear storage** on it, deletes `/sdcard/Android/data/<package>/`. Push your snapshot back before the next launch:

```powershell
$s="<repo>\new_version\snapshots\<snap>\external"; $p="<package>"
cd C:\LDPlayer\LDPlayer9
.\adb.exe push "$s\." /sdcard/Android/data/$p/files/
.\adb.exe shell "find /sdcard/Android/data/$p/files -type f | wc -l"
```

Taking a snapshot of a device is the same copy in the other direction (`adb pull`).

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
| Language | `070001`, `070002` | Per-language text packs replayed from recordings (English recorded) |
| File URLs | `020002` | Recorded URLs are reused; for unseen hashes, URLs pointing back at this server are invented |
| Ads | host block, `050018` | Ad hosts are blocked; the reward claim returns `False` |
| Anything else | | Replays the last recorded reply, or prints `UNKNOWN command` |

## The real-CDN fallback

When the game asks the CDN for a file the server does not have, the server can forward that one request to the real CDN, keep the reply, and serve it from local storage from then on. This is a safety net for gaps in your recordings, and it is the one case where the server talks to the real internet. It does not replace the first-launch recording, which is required (see **Before you start**).

**How a CDN request is answered, in order:**

| Step | Source | Notes |
|---|---|---|
| 1 | The game's data folder (`snapshots` or `gamedata`) | Files pulled from a device, named by hash |
| 2 | `cdn_extra/` | Files extracted from your `.flow` recordings on startup, plus anything the fallback cached |
| 3 | The real CDN | If the CDN is still up, a 200 reply is saved to `cdn_extra/` |
| 4 | A 404 | The game shows "Error while trying to access CDN server" and keeps loading |

**What you see in the terminal:**

- `cdn served <hash>.. (N bytes)`: answered locally.
- `cdn MISSING <hash> <path> -> real CDN, will cache`, then `cdn cached <uuid>.. (N bytes)`: fetched once and saved.

**Why it can fetch files you never downloaded.** The server keeps the recorded `020002` reply, which lists the real CDN URL for every file in the catalog. The game asks for those URLs at boot. So a file from a chapter you never opened can still be requested at its real address, as long as the real CDN still serves it.

**It only works while the real CDN is up.** If the CDN host goes offline, or the publisher stops serving the files or starts signing and expiring the URLs, the fallback fails. Nothing gets cached, step 3 returns an error, and the game stops at the CDN error screen. After that, the only files available are the ones already on disk: the data folder, `cdn_extra/`, and the bodies inside your recordings. A file counts as preserved once it is local, meaning a `cached` line was printed or it is in the data folder.

**Intended use.** The fallback recovers files the game already asked for. It is not a way to download content your own account has not unlocked, and it is not guaranteed to keep working. Record anything you want to keep through the normal route (see **Recording what is missing**) while the real server is still up.

Back up `cdn_extra/` together with your snapshots. It holds every file the fallback has saved, and those files are only safe once they are local.

The API side works the same way. API calls are never forwarded, so a command the game sends but you never recorded prints `UNKNOWN command` and gets an empty reply.

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

## Recording what is missing

Everything the fake server knows came from real sessions recorded while the real server was still up. To fill a gap:

1. In an emulator instance with the game's data cleared, run `mitmweb --listen-port 8080 -w <name>.flow` (without the script).
2. Play the part that is missing. Let every download finish.
3. Stop mitmweb with Ctrl+C so the file saves. Move it into `captures`.

The first-launch recording is covered in **Before you start**. The same method fills later gaps: record the part that's missing, then pull the data folder again.

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| `No module named 'msgpack'` in mitmweb | mitmweb is not running from the venv. Run `pip install -r requirements.txt` inside the venv and start `mitmweb` from it |
| `Error while trying to access CDN server`, stuck loading | A file is missing. Check the terminal for `cdn MISSING` and see **The real-CDN fallback** |
| `cdn MISSING ... -> real CDN, will cache` then `cached` | Working as designed: the file was fetched once from the real CDN and stored in `cdn_extra` |
| `cdn MISSING` and no `cached` line | The real CDN refused it or is gone. Record that file from a real session while the server is up |
| `UNKNOWN command XXXXXX` | A reply you have not recorded. Record a session through the real server, or find the response shape in the il2cpp dump |
| Game returns to chapter 1 after closing | The saved chapter was overwritten. `050008` must only move progress forward, and `chapter_id` in the save must match the `data` blob |
| Ad button loops forever | The ad hosts are not being blocked. Restart mitmweb and the game |
| Game restarts at the language screen | Normal after clearing the app's data. Pick the same language |

## Doing this for another game from the same studio

Games from the studio share the same hosts and a very similar API, so the server is mostly game-independent. Expect small per-game differences.

1. Set `package` (and `data_dir`) in the config. Use a separate folder per game for recordings, snapshots and state.
2. Record a clean first launch through the real server first, then play as far as you can with the proxy on, so CDN bodies end up in the recordings.
3. Run the server and watch for `UNKNOWN command` lines. A command may exist in one game's recordings and not another's, so add a handler or record more.
4. Check the per-game parts against the table above: the catalog, the chapter list, the save blob, the exchange asset IDs, and game-specific features such as premium choices.

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

## Reverse-engineering notes

- Engine: Unity IL2CPP, arm64 only. The base APK holds `global-metadata.dat`; the split APK holds `libil2cpp.so`. Tools: Il2CppDumper, Ghidra with the dumper's script.
- Network code: the API client is `FPPOOLFBDBH`, built by `IFCJFFGGLME`. The URL comes from `BPODNMBNGML`, which keeps its strings as encrypted byte arrays and decrypts them with a repeating-key XOR (key array of 128 bytes, in the same file).
- In `global-metadata.dat` of this build: key array at offset 6057576, API URL array at 6078176 (48 bytes), OAuth URL array at 6078344 (56 bytes).
- API: MessagePack. A request is a list of command objects (`{"id": "050001", ...}`) and the reply is a dict keyed by command ID.
- Game catalog: `drama.dat` (a header, then a raw deflate stream from byte 31) lists file hashes in chapter order. The first 8 entries are shared files. It lists 376 hashes, and the server's `020002` list covers about 1,121.
- Ads: LevelPlay (ironSource) through Unity mediation.