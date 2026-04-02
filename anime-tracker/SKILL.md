---
name: anime-tracker
description: Track seasonal anime from mikanani.me, manage per-user subscriptions, poll RSS feeds for updates, dedupe candidate releases and downloaded files, submit OpenList/AList offline download jobs, handle download-complete callbacks, organize downloaded episodes into a media library, generate Kodi/Jellyfin-style NFO metadata, and record downloaded episodes to avoid duplicates. Use when the user asks what anime are in a given season/month, wants to subscribe to anime, wants recurring update checks, wants to judge duplicate releases before queueing, wants to queue downloads into AList/OpenList, wants callback-driven post-processing after download, or wants downloaded episodes tracked and organized into a library.
---

# Anime Tracker

Track seasonal anime from 蜜柑计划 and automate stateful download workflow.

## Workflow

1. Use `run_skill_script` with `skill_name="anime-tracker"` and `script_path="scripts/run.sh"`.
2. Set `BUGO_ANIME_CMD`.
3. Set `BUGO_STATE_PATH` to a writable JSON state file.
4. For OpenList integration, set `BUGO_OPENLIST_BASE_URL`.
5. For real tracking automation, create a runtime schedule job after subscriptions are created so `check-updates` runs periodically without waiting for the user to ask again.
6. Read compact JSON from stdout.

## Commands

- `season-list`: list a season from mikan
- `search`: search mikan
- `subscribe`: subscribe anime names into state
- `list-subscriptions`: show current subscriptions
- `check-updates`: poll RSS and return candidate releases for the assistant to judge; script only records feed observations and does not decide episode-level dedupe or auto-queue
- `queue-downloads`: queue selected GUIDs or torrent URLs into OpenList after the assistant finishes duplicate/quality judgement
- `mark-downloaded`: manually mark RSS GUIDs as downloaded
- `inspect-openlist`: inspect one OpenList path
- `process-downloads`: inspect downloaded files and perform move/NFO/scrape only after the assistant explicitly decides the files should be organized
- `handle-callback`: accept callback payload JSON or file names, but still require the assistant to decide whether matched files should actually be organized

## Required env

- `BUGO_ANIME_CMD`
- `BUGO_STATE_PATH`

## Common optional env

- `BUGO_YEAR`
- `BUGO_SEASON`: supports `春 夏 秋 冬`, `1月 4月 7月 10月`, `spring summer autumn fall winter`
- `BUGO_EXCLUDE_SUBSCRIBED=1`
- `BUGO_QUERY`
- `BUGO_ANIME_NAMES`: newline-separated anime names
- `BUGO_DEFAULT_SUBGROUP`: if set, subscribe directly to one mikan subgroup RSS
- `BUGO_SUBGROUP_PREFERENCE`: newline-separated preferred字幕组名称，供 assistant 做候选排序参考；脚本本身不再负责最终去重决策
- `BUGO_CHECK_LIMIT`: default `30`
- `BUGO_PREFERRED_QUALITY_RE`: regex to prefer specific release naming

## OpenList env

- `BUGO_OPENLIST_BASE_URL`
- `BUGO_OPENLIST_TOOL`: OpenList offline tool name, your instance verified value is `qBittorrent`, default `qBittorrent`
- `BUGO_OPENLIST_DELETE_POLICY`: default `delete_on_upload_succeed`
- `BUGO_DOWNLOAD_DIR`: default `/media/downloaded`
- `BUGO_LIBRARY_DIR`: default `/media/data`
- `BUGO_OPENLIST_PATH`: path for `inspect-openlist`


## Post-download env

- `BUGO_ORGANIZE_FROM`: source incoming dir, default `BUGO_DOWNLOAD_DIR`
- `BUGO_ORGANIZE_DRY_RUN=1`: preview only
- `BUGO_PROCESS_ONLY_NAMES`: newline-separated file names that the assistant has already approved for organization
- `BUGO_CALLBACK_PAYLOAD`: JSON callback body for `handle-callback`

## Behavior notes

- State is durable in `BUGO_STATE_PATH`.
- `check-updates` only gathers feed candidates and stores observations in `seen_items`. It does not perform final episode-level dedupe and does not auto-queue downloads.
- The assistant must judge duplicates itself by combining subscription aliases, episode parsing, subgroup preference, prior state, and OpenList inspection before queueing anything.
- Use `queue-downloads` only after the assistant has selected the exact GUIDs or torrent URLs that should be queued.
- `process-downloads` is not an autonomous organizer anymore. The assistant must first inspect download results, judge whether files are complete/non-duplicate/correctly matched, and only then call it with approved file names.
- Move decisions, writing `tvshow.nfo` / episode `.nfo`, and metadata scraping are assistant-governed decisions, not blind script defaults.
- `process-downloads` still matches files against subscribed anime using stored aliases and normalized names once the assistant has approved the file set.
- Successful organization also marks matching RSS items as downloaded.
- Metadata scraping currently uses Jikan search to generate simple NFO files. This is a pragmatic scraper bridge for Jellyfin/Kodi-style libraries.
- Queueing uses `/api/fs/add_offline_download` and depends on the configured OpenList offline backend actually being reachable. Your current OpenList instance was verified to accept `BUGO_OPENLIST_TOOL=qBittorrent`.
- After `subscribe`, do not stop at writing state. Create a periodic runtime job so the system keeps checking feeds automatically.
- Recommended automation pattern: schedule `check-updates` every few hours, let the assistant decide which items are real new episodes, then call `queue-downloads`; after downloads appear, let the assistant inspect completed files, decide which ones should be organized, and only then call `process-downloads` or `handle-callback`.

## Anti-duplicate workflow

1. Never queue directly from `check-updates` output. First group candidates by anime + episode, then keep only one preferred release per episode.
2. Deduping order must be: already in library > already marked in `downloaded_items` > already present in `/media/downloaded` > new candidate.
3. Before queueing, inspect both `/media/data` and `/media/downloaded` through OpenList. If the same episode is already in library, do not queue any new release for that episode.
4. If the same episode already exists in `/media/downloaded`, compare releases and keep only the best one by subgroup preference, quality, subtitle preference, and container; do not queue another lower-priority copy.
5. If multiple files for one episode are already in `/media/downloaded`, delete the losing copies before running `process-downloads`. Keep only the final approved file set.
6. Approved file set should be explicit. Pass only approved names via `BUGO_PROCESS_ONLY_NAMES`; never let `process-downloads` scan a messy download directory blindly.
7. Always dry-run mentally or with `BUGO_ORGANIZE_DRY_RUN=1` when episode parsing looks suspicious. Example: titles like `Oshi no Ko S3 - 10` can be misread if alias/season logic is weak.
8. If script matching is wrong, prefer manual OpenList move + rename + NFO write over blind automation. Correctness is more important than full automation.
9. After manual cleanup or manual organization, update state consistently: keep `processed_files`, `downloaded_items`, and history aligned so future dedupe decisions see the true latest state.
10. For this workspace, the proven safe pattern is: inspect candidates -> queue only winners -> inspect `/media/downloaded` -> delete duplicate downloads -> dry-run organization on the kept files -> actual move/NFO/scrape -> verify `/media/downloaded` is empty or only contains unresolved files.
