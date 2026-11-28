"""Tests for Trailblazer's whole-folder (season) pairing. No ffmpeg or Anki needed.
Run:  python3 tests/test_season.py
Example numbers refer to section 4 of SPEC.md."""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import trailblazer as tb


def row(rows, video):
    return next(r for r in rows if r["video"] == video)


def test_episode_numbers_are_read_from_common_names():
    assert tb.episode_key("Show S01E03.mkv") == (1, 3)
    assert tb.episode_key("show.s1e3.720p.mkv") == (1, 3)
    assert tb.episode_key("Serie.1x04.mkv") == (1, 4)
    assert tb.episode_key("Serie - E07.mp4") == (None, 7)
    assert tb.episode_key("Serie Ep 8.mp4") == (None, 8)
    assert tb.episode_key("Serie Episode 9.mp4") == (None, 9)
    assert tb.episode_key("ep3.mkv") == (None, 3)


def test_resolutions_and_codecs_are_not_episode_numbers():
    assert tb.episode_key("Film 1920x1080 x264.mkv") is None
    assert tb.episode_key("bonus.mp4") is None
    assert tb.episode_key("Serie HEVC.mkv") is None


def test_example_1_ten_episodes_with_sidecars():
    files = ["Show S01E%02d.mkv" % i for i in range(1, 11)] + ["Show S01E%02d.es.srt" % i for i in range(1, 11)]
    rows = tb.plan_season(files, {}, "es", "")
    assert len(rows) == 10
    assert all(r["ticked"] for r in rows)
    assert [r["number"] for r in rows] == ["S01E%02d" % i for i in range(1, 11)]
    for r in rows:
        assert r["target"]["name"] == r["episode"] + ".es.srt"


def test_example_2_paired_by_number_when_names_differ():
    rows = tb.plan_season(["Serie.1x04.mkv", "Serie - S01E04 - Spanish.srt"], {}, "es", "")
    assert rows[0]["target"]["name"] == "Serie - S01E04 - Spanish.srt"
    assert rows[0]["ticked"]


def test_example_3_embedded_track_when_no_file():
    emb = {"ep3.mkv": [{"n": 0, "lang": "eng", "text": True}, {"n": 1, "lang": "spa", "text": True}]}
    rows = tb.plan_season(["ep3.mkv"], emb, "es", "en")
    assert rows[0]["target"]["src"] == "emb:1"
    assert rows[0]["trans"]["src"] == "emb:0"


def test_image_subtitle_tracks_are_not_used():
    emb = {"ep3.mkv": [{"n": 0, "lang": "spa", "text": False}]}
    rows = tb.plan_season(["ep3.mkv"], emb, "es", "")
    assert rows[0]["target"] is None and "no subtitles" in rows[0]["notes"]


def test_example_4_separate_file_beats_embedded():
    emb = {"Show S01E05.mkv": [{"n": 0, "lang": "spa", "text": True}]}
    rows = tb.plan_season(["Show S01E05.mkv", "Show S01E05.es.srt"], emb, "es", "")
    assert rows[0]["target"]["src"] == "file:Show S01E05.es.srt"


def test_example_5_missing_subtitles_unticks_only_that_episode():
    files = ["Show S01E06.mkv", "Show S01E06.es.srt", "Show S01E07.mkv", "Show S01E07.en.srt"]
    rows = tb.plan_season(files, {}, "es", "")
    assert row(rows, "Show S01E06.mkv")["ticked"]
    r7 = row(rows, "Show S01E07.mkv")
    assert not r7["ticked"] and "no subtitles" in r7["notes"]


def test_example_6_built_episodes_start_unticked():
    files = ["Show S01E%02d.mkv" % i for i in range(1, 11)] + ["Show S01E%02d.es.srt" % i for i in range(1, 11)]
    rec = tb.record_built(None, "Show", [("Show S01E%02d" % i, 300) for i in range(1, 5)], "2026-11-28")
    rows = tb.plan_season(files, {}, "es", "", rec, "Show")
    for r in rows[:4]:
        assert not r["ticked"] and "built on 2026-11-28" in r["notes"]
    assert all(r["ticked"] for r in rows[4:])


def test_example_7_record_matches_on_deck_name():
    files = ["Show S01E01.mkv", "Show S01E01.es.srt"]
    rec = tb.record_built(None, "Show", [("Show S01E01", 300)], "2026-11-28")
    rows = tb.plan_season(files, {}, "es", "", rec, "Show 2")
    assert rows[0]["ticked"]


def test_record_replaces_an_earlier_entry_for_the_same_episode():
    rec = tb.record_built(None, "Show", [("Show S01E01", 300)], "2026-11-01")
    rec = tb.record_built(rec, "Show", [("Show S01E01", 310), ("Show S01E02", 290)], "2026-11-28")
    assert len(rec["built"]) == 2
    assert tb.built_on(rec, "Show", "Show S01E01") == "2026-11-28"


def test_example_9_no_number_listed_last_and_unticked():
    files = ["bonus.mp4", "Show S01E01.mkv", "Show S01E01.es.srt"]
    rows = tb.plan_season(files, {}, "es", "")
    assert rows[-1]["video"] == "bonus.mp4"
    assert not rows[-1]["ticked"]
    assert "no episode number" in rows[-1]["notes"]


def test_no_number_file_still_pairs_by_name():
    rows = tb.plan_season(["bonus.mp4", "bonus.es.srt"], {}, "es", "")
    assert rows[0]["target"]["name"] == "bonus.es.srt"


def test_duplicate_episode_numbers_are_unticked():
    files = ["Show S01E02.mkv", "Show S01E02 (copy).mp4", "Show S01E02.es.srt"]
    rows = tb.plan_season(files, {}, "es", "")
    assert all(not r["ticked"] and "duplicate episode" in r["notes"] for r in rows)


def test_two_files_in_the_language_uses_first_and_says_so():
    files = ["Show S01E01.mkv", "Show S01E01.es.srt", "Show S01E01.forced.es.srt"]
    rows = tb.plan_season(files, {}, "es", "")
    assert rows[0]["target"]["name"] == "Show S01E01.es.srt"
    assert "2 found" in rows[0]["notes"]


def test_unmarked_file_is_used_for_target_but_never_translation():
    rows = tb.plan_season(["Show S01E01.mkv", "Show S01E01.srt"], {}, "es", "en")
    assert rows[0]["target"]["name"] == "Show S01E01.srt"
    assert "language not marked in file name" in rows[0]["notes"]
    assert rows[0]["trans"] is None


def test_translation_is_paired_and_missing_translation_is_fine():
    files = ["Show S01E01.mkv", "Show S01E01.es.srt", "Show S01E01.en.srt",
             "Show S01E02.mkv", "Show S01E02.es.srt"]
    rows = tb.plan_season(files, {}, "es", "en")
    assert rows[0]["trans"]["name"] == "Show S01E01.en.srt"
    assert rows[1]["trans"] is None and rows[1]["ticked"]


def test_episode_1_does_not_take_episode_10s_subtitles():
    files = ["Show S01E1.mkv", "Show S01E10.mkv", "Show S01E10.es.srt"]
    rows = tb.plan_season(files, {}, "es", "")
    assert row(rows, "Show S01E1.mkv")["target"] is None
    assert row(rows, "Show S01E10.mkv")["target"]["name"] == "Show S01E10.es.srt"


def test_show_name_is_not_read_as_a_language():
    files = ["The Spanish Princess S01E01.mkv", "The Spanish Princess S01E01.en.srt"]
    rows = tb.plan_season(files, {}, "es", "")
    assert rows[0]["target"] is None


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print("ok    ", name)
        except Exception as e:
            failed += 1
            print("FAILED", name, repr(e))
    print("%d passed, %d failed" % (len(tests) - failed, failed))
    sys.exit(1 if failed else 0)
