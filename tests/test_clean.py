"""Tests for Trailblazer's subtitle clean-up. No ffmpeg or Anki needed.   Run:  python3 tests/test_clean.py"""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import trailblazer as tb


def test_caption_inside_a_line_is_removed():
    assert tb.clean_text("(MUJER) Vamos a la playa.", True) == "Vamos a la playa."
    assert tb.clean_text("-(SOLLOZANDO) No lo sé.", True) == "- No lo sé."
    assert tb.clean_text("No. (MÚSICA SUAVE)", True) == "No."


def test_line_that_is_only_captions_is_dropped():
    assert tb.clean_text("(EMISORA)", True) == ""
    assert tb.clean_text("- (RÍE) (TOSE)", True) == ""
    assert tb.clean_text("[door slams] ♪", True) == ""


def test_spoken_brackets_are_kept():
    assert tb.clean_text("Vamos (creo) a la playa.", True) == "Vamos (creo) a la playa."
    assert tb.clean_text("Fue en (1998).", True) == "Fue en (1998)."


def test_option_off_leaves_captions():
    assert tb.clean_text("(MUJER) Hola.", False) == "(MUJER) Hola."


def test_clip_span_pads_and_trims():
    assert tb.clip_span(5000, 7000, 0, 400) == (5000, 7400)
    assert tb.clip_span(5000, 7000, -300, 400) == (5300, 7400)        # negative before trims the start
    assert tb.clip_span(100, 900, 250, 0) == (0, 900)
    assert tb.clip_span(5000, 5400, -300, -300) == (5000, 5400)       # too little left: use the line as timed


def test_a_sung_line_is_dropped_whole():
    assert tb.clean_text("♪ Bella ciao, bella ciao ♪", True) == ""
    assert tb.clean_text("♪ Una mañana me he levantado", True) == ""          # only an opening note
    assert tb.clean_text("♪ Bella ciao", False) == "♪ Bella ciao"


def _cue(start, end, text):
    return {"start": start, "end": end, "text": text}


def test_a_split_sentence_is_joined():
    out = tb.join_split([_cue(0, 2000, "A ver, quiero las máquinas funcionando"),
                         _cue(2100, 4000, "antes de las ocho."), _cue(4100, 5000, "Vale.")])
    assert [(c["start"], c["end"], c["text"]) for c in out] == [
        (0, 4000, "A ver, quiero las máquinas funcionando antes de las ocho."), (4100, 5000, "Vale.")]


def test_whole_sentences_and_dialogue_are_not_joined():
    keep = [_cue(0, 1000, "No lo sé."), _cue(1100, 2000, "vamos"),            # earlier line is finished
            _cue(2100, 3000, "Vamos a ver"), _cue(3100, 4000, "Tokio, ven."),  # next starts with a capital
            _cue(4100, 5000, "-Hola, tío"), _cue(5100, 6000, "-qué tal."),      # dialogue dashes
            _cue(6100, 7000, "Y entonces"), _cue(9000, 9900, "se fue.")]        # long pause between
    assert [c["text"] for c in tb.join_split(keep)] == [c["text"] for c in keep]


def test_joining_stops_at_three_lines_and_twelve_seconds():
    four = [_cue(i * 1000, i * 1000 + 900, t) for i, t in enumerate(["uno", "dos", "tres", "cuatro."])]
    assert [c["text"] for c in tb.join_split(four)] == ["uno dos tres", "cuatro."]
    slow = [_cue(0, 7000, "Esto es muy"), _cue(7500, 13000, "largo.")]
    assert len(tb.join_split(slow)) == 2


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print("ok    ", name)
        except AssertionError as e:
            failed += 1
            print("FAILED", name, e)
    print("%d passed, %d failed" % (len(tests) - failed, failed))
    sys.exit(1 if failed else 0)
