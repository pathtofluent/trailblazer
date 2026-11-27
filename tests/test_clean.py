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
