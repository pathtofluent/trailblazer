---
project: Trailblazer
status: testing
owner: PathToFluent
type: Local browser app (Python)
created: 2026-11-28
updated: 2026-11-28
---

# Trailblazer: whole-folder import

This spec covers importing a whole season in one pass. The single-episode flow is described in `README.md` and `CHANGELOG.md` and is unchanged by it.

## 1. Goal
Making cards one episode at a time means ten rounds of picking files and pressing Create for a ten-episode season. Pointing Trailblazer at a folder should pair every video with its subtitles, show the pairing for a check, and build the whole season into one deck file in one go. Episodes already built are skipped unless asked for again.

## 2. How I'll use it
1. I start Trailblazer and choose **Whole folder** instead of One episode.
2. I pick the season's folder.
3. I pick the subtitle language I'm learning and, optionally, the translation language.
4. Trailblazer lists every episode it found: number, video, subtitles, translation, line count. Episodes already built and episodes with no subtitles start unticked.
5. I check the pairing, untick anything I don't want, set the deck name and audio padding, and press **Create season deck**.
6. A progress bar runs through the episodes. At the end I get one `.apkg` file and a note of anything that failed.
7. I double-click the file and Anki imports the cards.

## 3. Rules

Finding episodes
1. Whole-folder mode reads the folder chosen and nothing beneath it. Sub-folders are not searched.
2. Every video or audio file Trailblazer already accepts counts as an episode.
3. An episode's number is read from its file name, first match wins: `S01E03` / `s1e3`, then `1x03`, then `E03` / `Ep 3` / `Episode 3`. Case does not matter.
4. A file with none of those patterns gets no number. It is listed last, unticked, marked "no episode number", and can still be paired by hand-ticking only if its subtitles share its file name (rule 6).
5. Two videos with the same season and episode number are both listed unticked, marked "duplicate episode".

Pairing subtitles
6. A subtitle file belongs to a video if its name starts with the video's name (`Show S01E03.mp4` and `Show S01E03.es.srt`), or failing that, if it carries the same season and episode number.
7. Subtitles inside the video file (embedded text tracks) count too, matched by the track's language tag.
8. The language is chosen once for the whole folder. A file counts as that language if its name carries the code or name (`.es.`, `.spa.`, `Spanish`, `español`) or, for an embedded track, if its language tag matches.
8a. A subtitle file whose name carries no language at all is used for the language being learned only when that episode has no file marked with it, and the row says "language not marked in file name". An unmarked file is never used as the translation.
9. When an episode has both a separate file and an embedded track in the chosen language, the separate file wins.
10. When an episode has two candidates of the same kind in the chosen language, the first in alphabetical order is used and the row says "2 found".
11. An episode with no subtitles in the chosen language is listed unticked, marked "no subtitles".
12. The translation track follows rules 6 to 10 with the translation language. A missing translation is not an error; those cards simply have no translation.

Building
13. All ticked episodes go into one `.apkg` file and one deck. The deck name defaults to the folder's name and can be changed.
14. Each episode's label is its video's file name without the extension, the same default the single-episode flow uses. Cards made earlier one episode at a time are therefore updated, not duplicated, if built again into the same deck.
15. Each card is tagged `Trailblazer` and with its episode label, and its Source line names the episode and time, as now.
16. Clean-up, sentence joining, subtitle shift, audio padding, bitrate and snapshot size are set once and apply to every episode.
17. There is no line-by-line review in whole-folder mode.
18. If one episode fails (unreadable subtitles, ffmpeg error), it is left out, the others are still built, and the end screen names the episode and the reason.
19. Cancelling stops the run, writes no deck file and records nothing.
20. The file is saved in the season's folder, named `<deck name>.apkg`, or in Downloads if that folder can't be written to.

Skipping episodes already built
21. After a successful build, Trailblazer records each episode it built in `trailblazer_done.json` in the season's folder: the episode label, the deck name, the number of cards and the date.
22. When the folder is opened again, episodes in that record for the same deck name start unticked, marked "built on <date>". Ticking one builds it again.
23. If the folder can't be written to, the record goes beside the deck file instead, and the end screen says where.
24. The record is never used to delete or change anything in Anki. It only decides which rows start ticked.

## 4. Examples

| # | Given | Expected |
|---|-------|----------|
| 1 | `Show S01E01.mkv` … `Show S01E10.mkv` with `Show S01E01.es.srt` … `.es.srt` beside them | 10 rows, all ticked, each paired with its own `.es.srt` |
| 2 | `Serie.1x04.mkv` and `Serie - S01E04 - Spanish.srt` | Paired by number (rule 6, second half) |
| 3 | `ep3.mkv` with an embedded Spanish text track and no separate file | Paired with the embedded track |
| 4 | Episode 5 has `.es.srt` and an embedded Spanish track | The `.es.srt` is used (rule 9) |
| 5 | Episode 7 has no Spanish subtitles | Row unticked, "no subtitles"; the other episodes build |
| 6 | Episodes 1 to 4 built yesterday into deck "Show"; folder opened again with 6 more episodes added | Rows 1 to 4 unticked, "built on 2026-11-28"; rows 5 to 10 ticked |
| 7 | Same as 6, but the deck name changed to "Show 2" | All 10 rows ticked (rule 22 matches on deck name) |
| 8 | Episode 2's subtitle file is empty | Season built without episode 2; end screen: "S01E02: no subtitle lines found"; episode 2 not recorded |
| 9 | `bonus.mp4` with no episode number and no matching subtitles | Listed last, unticked, "no episode number" |
| 10 | Episode 3 was built earlier on its own, as `Show S01E03` in deck "Show" | Built again into deck "Show", its cards are updated in place, not duplicated |

## 5. Not doing
- Searching sub-folders, or several seasons in one pass.
- Line-by-line review in whole-folder mode (use One episode for that).
- One `.apkg` per episode, or a sub-deck per episode.
- Reading Anki to see what is already there. Trailblazer still never touches Anki directly.
- Downloading subtitles.

## 6. Inputs and outputs
- **Reads:** the chosen folder's video, audio and subtitle files; embedded text tracks via ffprobe/ffmpeg; `trailblazer_done.json` if present.
- **Writes:** `<deck name>.apkg` and `trailblazer_done.json` in the season's folder (fallbacks in rules 20 and 23).
- **Settings I can change:** deck name, target and translation language, the shared options in rule 16, which rows are ticked.

## 7. Where it runs
- macOS (also Windows and Linux as now), Python 3.8 or newer, ffmpeg and ffprobe. No new installs.
- Anki 25.09 or newer to import the file.

## 8. Decisions made

| Decision | Why |
|----------|-----|
| One `.apkg` for the whole season | One double-click to import (owner's choice, 2026-11-28) |
| Pairing list only, no line review | A season is too many lines to review by hand (owner's choice) |
| One deck per show, episodes told apart by tag | Suits Waypoint, which sorts across the deck (owner's choice) |
| Built episodes recorded in `trailblazer_done.json` beside the videos | Trailblazer can't read Anki; the record travels with the season (owner's choice) |
| Episode label is the file name, as in single-episode mode | Earlier single-episode imports are updated, not duplicated |
| A failed episode is skipped, not fatal | One bad subtitle file shouldn't cost the whole season |
| The season-finding and pairing logic is kept apart from the web server, with tests | It can be tested without ffmpeg or a browser |
| An unmarked subtitle file can serve as the language being learned (rule 8a) | Many seasons ship one `.srt` per episode with no language in the name |
| Language is read only from the part of a subtitle name after the video's name | A show called "The Spanish Princess" isn't read as Spanish |
| A subtitle that starts with two videos' names goes to the longer one; a name must end at a non-letter | `Show S01E1` never takes `Show S01E10.es.srt` |
| Episode numbers in `E03` form need no letter just before the E | `HEVC` and similar words aren't read as episodes |
| Image-based embedded tracks are never paired | Trailblazer can't read them |
| No version number until Stage 2 | Stage 1 changes nothing a person sees |
| Line counts are shown for subtitle files; embedded tracks say "later" and are counted when built | Reading an embedded track means running ffmpeg on the whole video for every row |
| An episode whose subtitle file has no lines is unticked in the list already, as well as failing at build time if ticked | The problem shows before the build, not after |
| With several audio tracks, the one tagged with the language being learned is used, else the first; the row names it | Dubbed releases often put English first |
| One-episode mode does not write `trailblazer_done.json` | The record is for seasons; one-episode builds are updated by re-import anyway |
| After a build the list is refreshed, so the episodes just built show "built on" | What the next run will do is visible at once |
| The season's deck file is saved as `<deck name>.apkg` in the season's folder | Rule 20 |

## 9. Open questions
- [ ] An episode built earlier on its own into a different deck is imported again as new cards, because a card's identity includes the deck name. Workaround: untick it. Whether to do more, and what: owner.

## 10. Build stages
- [x] **Stage 1:** Finding and pairing. Functions that take a folder listing and return the episode rows (rules 1 to 12, 21 to 22), with tests for examples 1 to 7 and 9. No interface yet.
- [x] **Stage 2:** Whole-folder mode in the browser: the mode switch, the pairing list, building one season deck with progress, the end screen and the record file (rules 13 to 20, 23). Examples 8 and 10 checked by hand on a made-up season.
- [ ] **Later:** Several seasons in one pass; choosing a different subtitle file for one row from the list.

## 11. How to check it works
- `python3 tests/test_season.py` for the pairing rules.
- A made-up three-episode season (one with embedded subtitles, one with none) built in the browser and imported into a separate test Anki profile.
- Not testable on the build machine: real series files and very large seasons. The owner tries a real season after Stage 2.

## 12. Instructions for Claude
- Read this whole file before writing anything.
- Build only the next unchecked stage, then stop and say what to test.
- If a rule is unclear or two rules conflict, ask before building. For small details not covered here, decide, and record the choice under "Decisions made".
- Check the examples in section 4 against the code and say which pass.
- Say plainly what could not be tested.
- When done, update: status, the stage checkboxes, "Decisions made", and the log.

## 13. Log
- 2026-11-28: Owner built a whole show (5 seasons, 48 episodes, 26,908 cards, 1.1 GB) into a test profile. Deck checked: every card has audio and a snapshot, no empty or caption lines, IDs unique. Found: two episodes built earlier on their own, under a different deck name, were imported again as new cards (rule 14 only covers the same deck). Noted as a known gap.
- 2026-11-28: Stage 2 built, released as 1.6.0. Tested in the browser on a made-up five-file season and imported into a separate test Anki profile: pairing by name and by number, embedded subtitles and translation, Spanish audio track chosen over English, empty and missing subtitles, no-number file, record written and episodes unticked on the next scan, one deck file. Examples 8 and 10 pass (10 in Anki: 2 added, 2 updated). Not tested: Cancel during a build (rule 19), an unwritable folder (rules 20, 23), a real season. Next: owner tries a real season.
- 2026-11-28: Stage 1 built: `episode_key`, `plan_season`, `record_built` and `built_on` in `trailblazer.py`; 19 tests in `tests/test_season.py`, all passing, covering examples 1 to 7 and 9. Rule 8a added. Next: Stage 2.
- 2026-11-28: Spec written for whole-folder import; four choices settled with the owner. Next: Stage 1.
