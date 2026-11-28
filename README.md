# PathToFluent Trailblazer

Turns a video and its subtitles into an Anki deck. Each subtitle line becomes one card: the scene's snapshot and audio clip on the front, the sentence on the back, with the translation hidden behind a Show translation button.

It runs on your own computer and opens in your browser. Nothing is uploaded.

Status: early, with light hands-on use on macOS.

## Run it

```
python3 trailblazer.py
```

Needs Python 3.8 or newer and ffmpeg (`brew install ffmpeg` on macOS, `winget install ffmpeg` on Windows, your package manager on Linux). No other installs.

## Use it

1. **Choose files.** Pick an episode or film, then the subtitles in the language you're learning and, optionally, a translation track. Subtitle files next to the video and text tracks inside it are found for you.
2. **Review.** Press play on any line to hear the clip and see the snapshot. Untick lines you don't want; click text to edit it. Set the extra audio before and after each line here and listen with play; a negative number trims the clip.
3. **Create the deck.** You get one `.apkg` file. Double-click it and Anki imports the cards, audio and images.

Speaker and sound captions such as [door slams] or (MUJER) are removed from the cards unless you turn that option off, and so are sung lines marked ♪. A sentence split across two or three subtitle lines is joined into one card; that is a separate option.

Reads .srt, .vtt and .ass subtitles. Image-based subtitles (most DVD and Blu-ray tracks) can't be read.

## A whole season at once

Choose **Whole folder** at the top and pick the season's folder.

1. Pick the language you're learning and, optionally, the translation language.
2. Trailblazer lists every video in the folder with the subtitles it paired it with: files beside the video that share its name or episode number (`S01E03`, `1x03`, `Episode 3`), or text tracks inside it. Rows with nothing to build, such as missing subtitles or no episode number, start unticked, with the reason shown.
3. Untick anything you don't want and press **Create season deck**. You get one `.apkg` file for the whole season, in one deck.

The options are set once for every episode, and there is no line-by-line review in this mode. Episodes already built are noted in `trailblazer_done.json` in the folder and start unticked next time. If a video has several audio tracks, the one in the language you're learning is used. Sub-folders aren't searched.

Importing the same episode again updates its cards instead of duplicating them.

## Cards

The note type is `PathToFluent Trailblazer`. Trailblazer fills Sequence, Sentence, Translation, Audio, Snapshot and Source; Notes is yours. The rest are filled in by Waypoint: Unknown Words, Labels, Lemma, Definition, Definition Monolingual and Dictionary Link. The back of the card shows the new word and its definition once Waypoint has supplied them.

If you made cards with an earlier Trailblazer, don't re-import them. In Anki, use Tools > PathToFluent Waypoint > Prepare a note type, which adds the new fields and layout to the cards you already have.

## The PathToFluent tools

| Tool | What it does |
|------|--------------|
| [Trailblazer](https://github.com/pathtofluent/trailblazer) | Turns a video and its subtitles into an Anki deck |
| [Waypoint](https://github.com/pathtofluent/waypoint) | Sorts sentence cards so the next one has exactly one unknown word |
| [Checkpoint](https://github.com/pathtofluent/checkpoint) | A single Complete button for chapter and lesson cards |
| [Scout](https://github.com/pathtofluent/scout) | Finds Netflix titles by country and original language |
| [Logbook](https://github.com/pathtofluent/logbook) | Logs your time with a language and tracks hours, known words and milestones |

## Licence

GNU AGPL v3 or later. See `LICENSE`.
