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

Speaker and sound captions such as [door slams] or (MUJER) are removed from the cards unless you turn that option off.

Reads .srt, .vtt and .ass subtitles. Image-based subtitles (most DVD and Blu-ray tracks) can't be read. One episode at a time.

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
