# Changelog

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
