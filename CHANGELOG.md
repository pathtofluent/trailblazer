# Changelog

## 1.6.0 (2026-11-28)
- New: **Whole folder** mode. Point Trailblazer at a season's folder and it pairs every video with its subtitles and translation, by file name or episode number (`S01E03`, `1x03`, `Episode 3`), using subtitle files beside the videos or text tracks inside them. Check the list, untick what you don't want, and get one deck file for the whole season.
- Episodes already built are recorded in `trailblazer_done.json` in the season's folder and start unticked next time. Tick one to build it again.
- An episode that fails is left out and named on the end screen; the rest are still built.
- When a video has several audio tracks, the one tagged with the language you're learning is used.
- Clean-up, joining, timing and audio options are set once for the whole season. There is no line-by-line review in this mode; use One episode for that.
- Cards are labelled with the video's file name, as in One episode mode, so an episode built earlier on its own is updated rather than duplicated when built again into the same deck.

## 1.5.0 (2026-11-28)
- A sung line marked with ♪ is now dropped whole. Before, only the note signs were removed and the lyric stayed as a card. Part of the existing clean-up option.
- New option, on by default: a sentence the subtitles split across two or three lines becomes one card with one clip. Lines are joined only when the earlier one stops without closing punctuation, the next starts in lower case, the pause is under a second and the whole is under twelve seconds. Dialogue lines starting with a dash are left alone.
- Re-importing an episode made with an earlier version adds the joined cards; the old second halves stay in Anki until removed by hand.

## 1.4.2 (2026-11-27)
- "Extra audio before / after" moved up beside the list of lines, where the ▶ preview uses it, so clip length can be set by ear before the deck is made.
- Either value may now be negative, which trims the clip. Useful when subtitles appear early and the clip catches the end of the previous line.
- Defaults changed from 250 / 250 ms to 0 / 400 ms.

## 1.4.1 (2026-11-27)
- The clean-up option now also removes speaker and sound captions in capitals inside round brackets, such as (MUJER) or (SOLLOZANDO), from the middle of a spoken line. Before, only a line that was nothing but a bracket was dropped. Brackets holding lower-case text are kept. Applies to both the sentence and the translation.

## 1.4.0 (2026-11-26)
- Cards gain four fields for Waypoint to fill: Lemma, Definition, Definition Monolingual and Dictionary Link. The back shows the new word with its definition, in your language or the one you're learning depending on a Waypoint tag.

## 1.3.0 (2026-11-26)
- Renamed from SubDeck. The note type is now called "PathToFluent Trailblazer" (same note type as before, so existing cards are unaffected).

## 1.2 (2026-11-21)
- Cards carry Unknown Words and Labels fields; the back shows the new word.

## 1.1 (2026-11-21)
- Front shows snapshot and audio only; sentence and hidden translation moved to the back.

## 1.0 (2026-11-21)
- First version.

## Known gaps
- A card's identity includes its deck name. An episode built into one deck and later into another is imported as new cards, not updated. Untick episodes already in Anki under another deck when building a season.
- Cancel during a whole-folder build, and a season folder that can't be written to, are untested.
