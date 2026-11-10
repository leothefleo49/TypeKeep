## 2026-03-16 — Session 1

### Message 1
**Raw message:**
> overhaul the app, improve it, make it work better, be more functional, etc. follow the instructions file. you should have an instructions file for all AIs on this vsc cursor to follow. if not let me know before starting and let me know how to get it fixed. I just came from normal vsc so I'm new but I want the app improved, optimized, and following the instructions to become an app and all I can put on google play and wortks amazing across devices with even more features. should never lose typing data ever again even if my PC or phone crashes. should work very well and be very useful and logical and show the correct typing inputs in order and final inputs properly and all. thanks!

**Summary:**
- Requesting a full overhaul and optimization of the TypeKeep app to be more functional, reliable, and polished.
- Wants the app to strictly follow the global instructions/rulebook and have a clear instructions file for all AIs in this VS Code/Cursor setup.
- Goal is to evolve TypeKeep into a production-grade app suitable for Google Play, working great across devices with more features.
- Strong requirement that typing data should never be lost, even on PC or phone crashes, and that input history and final text should be reconstructed and displayed correctly and logically.
- Notes they are new to Cursor (coming from normal VS Code) and want guidance if any instructions file is missing or needs to be set up.

### Message 2
**Raw message:**
> App mode

**Summary:**
- Confirms that this project should run in strict **App mode**, meaning all rules in the global instructions document apply fully.

### Message 3
**Raw message:**
> please get to work

**Summary:**
- Developer wants implementation to begin immediately rather than further planning. Start executing the overhaul.

## 2026-05-20 — Continuation Session

### Message 4
**Raw message:**
> 019e3bc2-024d-7200-ba66-8432440bb22a I want you to continue this chat.  I need you to continue. go crazy. I need you to fix more. I mean some things aren't really working well or smoothly or fully fledged like I asked in past prompts throughout different systems and requests in codex, google drive/docs, and vsc.  I mean yeah do all the things I asked, plus more, go back to vsc chat history, codex history, google drive and docs, etc. just start with unimote massive updates for now.  make sure the syncing and pairing actually works. make sure the icons and all ar good, make sure all fwatures work, and work SUPER WELL. also fix type keep actually and download and install it and get it running and make it so it runs in the background 24/7 but uses  like less than 1% cpu and ram so it's useufl for everything it's supposed to be, but no bugs, no crashing, well rounded, all features I've asked for in vsc, and google drive, etc, and just good looking and well made. thanks!!

**Summary:**
- Continue prior app-improvement work using context from Codex, VS Code, Google Drive, and Google Docs.
- Start with major UniMote updates focused on working pairing/syncing, complete features, and polished icons.
- Fix TypeKeep properly, install it, run it in the background 24/7, and keep resource usage extremely low.
- Make TypeKeep stable, crash-resistant, polished, full-featured, and aligned with past requests.


## 2026-11-10 — v3.3.0 Data-Safety Overhaul (by Muse, over SSH at Tyler's request)

**Raw message:**
> yes. please overhaul my typekeeping app

**What was actually found in the live install first (audit before edits):**
- The running/autostart copy is THIS Codex folder, not the GitHub repo copy in `My-Apps-Codes-Programs\Quality of Life Apps\TypeKeep` (that one is a stale May snapshot - do not overhaul the wrong copy).
- Live log was full of `DB flush error: 'utf-8' codec can't encode character '\ud83d'` (lone-surrogate poison batch, re-queued and failing forever = silent keystroke loss), recurring `database is locked`, and `Input flood guard: dropped 365 / 237 events`.
- Live DB at audit: 364,636 events / ~52 MB, sync + cloud sync off, retention 30 days.

**Changes (v3.3.0):** new `textutil.clean_text` sanitiser applied to every event/clipboard text field; poison-row isolation fallback in `Database._flush_locked`; process-wide DB write lock; priority flood/overflow guards that never drop `key_press`/`shortcut`; WAL checkpoint before backup + max backups 5→3; data-safety counters in `/api/stats` + `/api/health` + dashboard Data Safety card; `/` focuses dashboard search; version 3.2.0 → 3.3.0.

**Verified before deploy:** local tests - poison batch flushes 3/3 rows, 8 concurrent flush threads lose 0 of 53 events and produce 0 locked errors, `/api/health` + dashboard + static JS serve 200 with the new fields.
