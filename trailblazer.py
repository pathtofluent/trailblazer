#!/usr/bin/env python3
"""
PathToFluent Trailblazer - turn a video and its subtitles into an Anki deck.

Each subtitle line becomes one card with the spoken audio clip, a snapshot of
the scene on the front; the sentence on the back, with the translation hidden
behind a "Show translation" button if you supply a second subtitle track.

Requirements: Python 3.8+ and ffmpeg (macOS: `brew install ffmpeg`).
Run:          python3 trailblazer.py
The interface opens in your browser. Nothing leaves your computer.
"""
import argparse, base64, concurrent.futures, hashlib, html, json, os, re, secrets
import shutil, sqlite3, string, subprocess, sys, tempfile, threading, time
import unicodedata, webbrowser, zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

APP, VERSION = "PathToFluent Trailblazer", "1.5.0"
TOKEN = secrets.token_urlsafe(16)
MEDIA_EXT = {".mkv", ".mp4", ".m4v", ".avi", ".mov", ".webm", ".ts", ".flv", ".wmv", ".mpg",
             ".mpeg", ".mp3", ".m4a", ".m4b", ".aac", ".flac", ".ogg", ".opus", ".wav"}
SUB_EXT = {".srt", ".vtt", ".ass", ".ssa"}
TEXT_SUB_CODECS = {"subrip", "srt", "ass", "ssa", "webvtt", "mov_text", "text"}
MODEL_ID = 1763738100331          # fixed, so every deck shares one "Trailblazer" note type
STATE = {"video": None, "probe": None}
JOB = {"state": "idle", "done": 0, "total": 0, "message": "", "path": "", "failures": 0}
JOB_LOCK = threading.Lock()
CANCEL = threading.Event()


# ───────────────────────────── ffmpeg helpers ─────────────────────────────
def find_tool(name):
    exe = name + (".exe" if os.name == "nt" else "")
    found = shutil.which(name)
    if found:
        return found
    here = os.path.dirname(os.path.abspath(__file__))
    for d in (here, "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", os.path.expanduser("~/bin")):
        p = os.path.join(d, exe)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


FFMPEG, FFPROBE = find_tool("ffmpeg"), find_tool("ffprobe")


def run(cmd, timeout=None):
    kw = {}
    if os.name == "nt":
        kw["creationflags"] = 0x08000000   # no console window
    return subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=timeout, **kw)


def probe(path):
    r = run([FFPROBE, "-v", "error", "-print_format", "json", "-show_streams", "-show_format", path])
    if r.returncode != 0:
        raise ValueError("ffmpeg could not read that file: " + r.stderr.decode("utf-8", "replace")[-300:])
    info = json.loads(r.stdout.decode("utf-8", "replace") or "{}")
    audio, subs, has_video = [], [], False
    for s in info.get("streams", []):
        tags = {k.lower(): v for k, v in (s.get("tags") or {}).items()}
        label = " - ".join(x for x in (tags.get("language"), tags.get("title")) if x and x != "und")
        kind = s.get("codec_type")
        if kind == "video" and not (s.get("disposition") or {}).get("attached_pic"):
            has_video = True
        elif kind == "audio":
            audio.append({"n": len(audio), "label": label or "Track %d" % (len(audio) + 1),
                          "codec": s.get("codec_name", "")})
        elif kind == "subtitle":
            codec = s.get("codec_name", "")
            subs.append({"n": len(subs), "label": label or "Track %d" % (len(subs) + 1),
                         "codec": codec, "text": codec in TEXT_SUB_CODECS})
    try:
        duration = float(info.get("format", {}).get("duration") or 0)
    except ValueError:
        duration = 0
    folder, stem = os.path.dirname(path), os.path.splitext(os.path.basename(path))[0]
    sidecars = []
    try:
        for f in sorted(os.listdir(folder)):
            if os.path.splitext(f)[1].lower() in SUB_EXT and f.lower().startswith(stem.lower()):
                sidecars.append(os.path.join(folder, f))
    except OSError:
        pass
    return {"audio": audio, "subs": subs, "has_video": has_video, "duration": duration,
            "sidecars": sidecars, "stem": stem, "folder": folder}


# ───────────────────────────── subtitle parsing ─────────────────────────────
def read_text(path):
    data = open(path, "rb").read()
    if data[:3] == b"\xef\xbb\xbf":
        return data[3:].decode("utf-8", "replace")
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16", "replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252", "replace")


_T = r"(?:(\d+):)?(\d{1,2}):(\d{1,2})[.,](\d{1,3})"
CUE = re.compile(_T + r"\s*-->\s*" + _T)


def _ms(h, m, s, f):
    return ((int(h or 0) * 60 + int(m)) * 60 + int(s)) * 1000 + int(f.ljust(3, "0"))


def parse_srt_vtt(text):
    cues, cur = [], None
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        m = CUE.search(line)
        if m:
            if cur and cur["lines"] and cur["lines"][-1].strip().isdigit():
                cur["lines"].pop()               # cue number glued to the previous cue
            g = m.groups()
            cur = {"start": _ms(*g[:4]), "end": _ms(*g[4:]), "lines": []}
            cues.append(cur)
        elif cur is not None:
            if line.strip() == "":
                cur = None
            else:
                cur["lines"].append(line)
    return [{"start": c["start"], "end": c["end"], "text": " ".join(c["lines"])} for c in cues]


def parse_ass(text):
    cues, fmt, in_events = [], None, False
    for line in text.replace("\r", "").split("\n"):
        s = line.strip()
        if s.startswith("["):
            in_events = s.lower() == "[events]"
        elif in_events and s.lower().startswith("format:"):
            fmt = [x.strip().lower() for x in s[7:].split(",")]
        elif in_events and s.lower().startswith("dialogue:") and fmt:
            parts = s[9:].strip().split(",", len(fmt) - 1)
            if len(parts) < len(fmt):
                continue
            row = dict(zip(fmt, parts))
            body = row.get("text", "")
            if re.search(r"\\p[1-9]", body):     # vector drawing, not dialogue
                continue
            body = re.sub(r"\{[^}]*\}", "", body)
            body = re.sub(r"\\[Nnh]", " ", body)
            try:
                st, en = (_ass_time(row["start"]), _ass_time(row["end"]))
            except (KeyError, ValueError):
                continue
            cues.append({"start": st, "end": en, "text": body})
    return cues


def _ass_time(t):
    h, m, s = t.strip().split(":")
    return int(round((int(h) * 3600 + int(m) * 60 + float(s)) * 1000))


def parse_subs(text, ext=""):
    if ext in (".ass", ".ssa") or "[Script Info]" in text[:2000]:
        return parse_ass(text)
    return parse_srt_vtt(text)


def clean_text(t, strip_sfx):
    t = re.sub(r"\{\\[^}]*\}", "", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = html.unescape(t)
    if strip_sfx:
        if re.search(r"[♪♫]", t):                          # a sung line: the whole cue goes, words and all
            return ""
        t = re.sub(r"\[[^\]]*\]", "", t)
        if re.fullmatch(r"\s*[-–]?\s*\([^)]*\)\s*", t):
            t = ""
        # (MUJER), (SOLLOZANDO): a caption inside a spoken line. Letters, none of them lower-case.
        t = re.sub(r"\([^()]*\)", lambda m: "" if any(c.isalpha() for c in m.group())
                   and not any(c.islower() for c in m.group()) else m.group(), t)
    t = re.sub(r"\s+", " ", t).strip()
    return "" if re.fullmatch(r"[-–\s]*", t) else t


def tidy(cues, shift, strip_sfx):
    out = []
    for c in sorted(cues, key=lambda c: (c["start"], c["end"])):
        text = clean_text(c["text"], strip_sfx)
        st, en = c["start"] + shift, c["end"] + shift
        if not text or en <= st or en <= 0:
            continue
        st = max(0, st)
        if out and out[-1]["text"] == text and st - out[-1]["end"] <= 150:
            out[-1]["end"] = max(out[-1]["end"], en)      # repeated cue, merge
        else:
            out.append({"start": st, "end": en, "text": text})
    return out


JOIN_GAP_MS, JOIN_MAX_MS, JOIN_MAX_CUES = 1000, 12000, 3


def join_split(cues):
    """Put back together a sentence the subtitles cut across two or three cues.
    A cue is joined to the one before it only when the earlier one stops without closing punctuation
    (it ends in a letter, a digit or a comma), this one starts with a lower-case letter, the pause
    between them is short, and the result stays a reasonable length. Lines of dialogue starting
    with a dash are left alone."""
    out = []
    for c in cues:
        prev = out[-1] if out else None
        if prev and prev.get("parts", 1) < JOIN_MAX_CUES and c["start"] - prev["end"] <= JOIN_GAP_MS \
                and c["end"] - prev["start"] <= JOIN_MAX_MS \
                and (prev["text"][-1].isalnum() or prev["text"][-1] == ",") \
                and c["text"][0].islower() and "-" not in (prev["text"][0], c["text"][0]) \
                and "–" not in (prev["text"][0], c["text"][0]):
            prev["text"], prev["end"] = prev["text"] + " " + c["text"], max(prev["end"], c["end"])
            prev["parts"] = prev.get("parts", 1) + 1
        else:
            out.append(dict(c))
    for c in out:
        c.pop("parts", None)
    return out


def pair(target, trans):
    j0 = 0
    for ln in target:
        hits = []
        while j0 < len(trans) and trans[j0]["end"] <= ln["start"] - 5000:
            j0 += 1
        for t in trans[j0:]:
            if t["start"] >= ln["end"]:
                break
            overlap = min(ln["end"], t["end"]) - max(ln["start"], t["start"])
            shorter = min(ln["end"] - ln["start"], t["end"] - t["start"])
            if overlap > 0 and overlap >= 0.4 * shorter:
                hits.append(t["text"])
        ln["trans"] = " ".join(hits)
    return target


def load_source(video, src):
    """src is 'file:<path>' or 'emb:<n>' (embedded subtitle track n)."""
    if src.startswith("file:"):
        path = src[5:]
        return parse_subs(read_text(path), os.path.splitext(path)[1].lower())
    n = int(src[4:])
    r = run([FFMPEG, "-v", "error", "-i", video, "-map", "0:s:%d" % n, "-f", "srt", "pipe:1"])
    if r.returncode != 0 or not r.stdout:
        raise ValueError("Could not read that embedded subtitle track (it may be image-based).")
    return parse_srt_vtt(r.stdout.decode("utf-8", "replace"))


# ───────────────────────────── Anki package writer ─────────────────────────────
CARD_CSS = """.card{font-family:-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;font-size:22px;
text-align:center;color:#1c1c1e;background:#fafafa;margin:0;padding:16px}
.nightMode.card,.night_mode.card{color:#ececec;background:#1e1e20}
.sd img{max-width:100%;max-height:45vh;border-radius:10px}
.sentence{font-size:1.25em;line-height:1.4;margin:18px 6px}
.trbtn{font-size:.7em;padding:8px 18px;border-radius:999px;border:1px solid #8884;background:transparent;
color:inherit;cursor:pointer;margin:4px}
.tr{display:none;margin:14px 6px;font-size:.9em;opacity:.8}
.new{font-size:.75em;margin:0 6px 10px;color:#2f6f5e;font-weight:600}
.lemma{font-weight:400;opacity:.75}
.def{margin:8px 10px 12px;font-size:.85em;line-height:1.45}
.wp .def.mono,.wp .enbtn{display:none}
.wp[data-tags~="waypoint_monolingual"] .def.mono{display:block}
.wp[data-tags~="waypoint_monolingual"] .def.bi{display:none}
.wp[data-tags~="waypoint_monolingual"] .enbtn{display:inline-block}
.dict{font-size:.6em;margin:4px 0 12px}.dict a{color:inherit;opacity:.6}
.notes{font-size:.8em;margin-top:10px}.src{font-size:.5em;opacity:.45;margin-top:18px}"""
CARD_FRONT = """<div class="sd">
{{#Snapshot}}<div class="img">{{Snapshot}}</div>{{/Snapshot}}
<div class="audio">{{Audio}}</div>
{{^Audio}}{{^Snapshot}}<div class="sentence">{{Sentence}}</div>{{/Snapshot}}{{/Audio}}
</div>"""
CARD_BACK = """<div class="sd wp" data-tags="{{Tags}}">
{{#Snapshot}}<div class="img">{{Snapshot}}</div>{{/Snapshot}}
<div class="audio">{{Audio}}</div>
<div class="sentence">{{Sentence}}</div>
{{#Unknown Words}}<div class="new">New: {{Unknown Words}}{{#Lemma}} <span class="lemma">({{Lemma}})</span>{{/Lemma}}</div>
{{#Definition Monolingual}}<div class="def mono">{{Definition Monolingual}}</div>{{/Definition Monolingual}}
{{#Definition}}<div class="def bi">{{Definition}}</div>
<button class="trbtn enbtn" onclick="var d=this.previousElementSibling,s=d.style.display==='block';d.style.display=s?'none':'block';this.textContent=s?'Show English':'Hide English';">Show English</button>{{/Definition}}
{{#Dictionary Link}}<div class="dict">{{Dictionary Link}}</div>{{/Dictionary Link}}{{/Unknown Words}}
{{#Translation}}<button class="trbtn" onclick="var t=this.nextElementSibling,s=t.style.display==='block';t.style.display=s?'none':'block';this.textContent=s?'Show translation':'Hide translation';">Show translation</button>
<div class="tr">{{Translation}}</div>{{/Translation}}
{{#Notes}}<div class="notes">{{Notes}}</div>{{/Notes}}
<div class="src">{{Source}}</div>
</div>"""
# Keep the layout and fields in step with PathToFluent Waypoint (its addon/layout.py).
FIELDS = ["Sequence", "Sentence", "Translation", "Audio", "Snapshot", "Source", "Notes",
          "Unknown Words", "Labels", "Lemma", "Definition", "Definition Monolingual", "Dictionary Link"]
SCHEMA = """
CREATE TABLE col (id integer primary key, crt integer not null, mod integer not null, scm integer not null,
 ver integer not null, dty integer not null, usn integer not null, ls integer not null, conf text not null,
 models text not null, decks text not null, dconf text not null, tags text not null);
CREATE TABLE notes (id integer primary key, guid text not null, mid integer not null, mod integer not null,
 usn integer not null, tags text not null, flds text not null, sfld integer not null, csum integer not null,
 flags integer not null, data text not null);
CREATE TABLE cards (id integer primary key, nid integer not null, did integer not null, ord integer not null,
 mod integer not null, usn integer not null, type integer not null, queue integer not null, due integer not null,
 ivl integer not null, factor integer not null, reps integer not null, lapses integer not null,
 left integer not null, odue integer not null, odid integer not null, flags integer not null, data text not null);
CREATE TABLE revlog (id integer primary key, cid integer not null, usn integer not null, ease integer not null,
 ivl integer not null, lastIvl integer not null, factor integer not null, time integer not null, type integer not null);
CREATE TABLE graves (usn integer not null, oid integer not null, type integer not null);
CREATE INDEX ix_notes_usn on notes (usn); CREATE INDEX ix_cards_usn on cards (usn);
CREATE INDEX ix_revlog_usn on revlog (usn); CREATE INDEX ix_cards_nid on cards (nid);
CREATE INDEX ix_cards_sched on cards (did, queue, due); CREATE INDEX ix_revlog_cid on revlog (cid);
CREATE INDEX ix_notes_csum on notes (csum);
"""


def stable_id(text, floor=1 << 30):
    return floor + int(hashlib.sha1(text.encode("utf-8")).hexdigest()[:10], 16) % (1 << 40)


def write_apkg(out_path, deck_name, notes, media_dir, media_files):
    """notes: list of dicts with keys guid, fields (list matching FIELDS), tags (list)."""
    now, deck_id = int(time.time()), stable_id("deck:" + deck_name)
    deck = lambda did, name: {"collapsed": False, "conf": 1, "desc": "", "dyn": 0, "extendNew": 0,
                              "extendRev": 50, "id": did, "lrnToday": [0, 0], "mod": now, "name": name,
                              "newToday": [0, 0], "revToday": [0, 0], "timeToday": [0, 0], "usn": -1}
    model = {"css": CARD_CSS, "did": deck_id, "id": str(MODEL_ID), "name": "PathToFluent Trailblazer", "type": 0, "mod": now,
             "usn": -1, "sortf": 0, "tags": [], "vers": [], "latexsvg": False,
             "latexPre": "\\documentclass[12pt]{article}\n\\special{papersize=3in,5in}\n\\usepackage{amssymb,amsmath}\n"
                         "\\pagestyle{empty}\n\\setlength{\\parindent}{0in}\n\\begin{document}\n",
             "latexPost": "\\end{document}", "req": [[0, "any", [1, 3, 4]]],
             "flds": [{"font": "Arial", "media": [], "name": n, "ord": i, "rtl": False, "size": 20, "sticky": False}
                      for i, n in enumerate(FIELDS)],
             "tmpls": [{"name": "Card 1", "ord": 0, "qfmt": CARD_FRONT, "afmt": CARD_BACK, "bqfmt": "",
                        "bafmt": "", "did": None}]}
    conf = {"activeDecks": [1], "addToCur": True, "collapseTime": 1200, "curDeck": 1, "curModel": str(MODEL_ID),
            "dueCounts": True, "estTimes": True, "newBury": True, "newSpread": 0, "nextPos": 1,
            "sortBackwards": False, "sortType": "noteFld", "timeLim": 0}
    dconf = {"1": {"autoplay": True, "id": 1, "maxTaken": 60, "mod": 0, "name": "Default", "replayq": True,
                   "timer": 0, "usn": 0,
                   "lapse": {"delays": [10], "leechAction": 0, "leechFails": 8, "minInt": 1, "mult": 0},
                   "new": {"bury": True, "delays": [1, 10], "initialFactor": 2500, "ints": [1, 4, 7], "order": 1,
                           "perDay": 20, "separate": True},
                   "rev": {"bury": True, "ease4": 1.3, "fuzz": 0.05, "ivlFct": 1, "maxIvl": 36500, "minSpace": 1,
                           "perDay": 100}}}
    tmp = tempfile.mkdtemp(prefix="trailblazer_db_")
    try:
        db_path = os.path.join(tmp, "collection.anki2")
        db = sqlite3.connect(db_path)
        db.executescript(SCHEMA)
        db.execute("INSERT INTO col VALUES (1,?,?,?,11,0,0,0,?,?,?,?,'{}')",
                   (now, now * 1000, now * 1000, json.dumps(conf), json.dumps({str(MODEL_ID): model}),
                    json.dumps({"1": deck(1, "Default"), str(deck_id): deck(deck_id, deck_name)}), json.dumps(dconf)))
        base = now * 1000
        for i, n in enumerate(notes):
            first = n["fields"][0]
            csum = int(hashlib.sha1(first.encode("utf-8")).hexdigest()[:8], 16)
            tags = (" " + " ".join(n["tags"]) + " ") if n["tags"] else ""
            db.execute("INSERT INTO notes VALUES (?,?,?,?,-1,?,?,?,?,0,'')",
                       (base + i, n["guid"], MODEL_ID, now, tags, "\x1f".join(n["fields"]), first, csum))
            db.execute("INSERT INTO cards VALUES (?,?,?,0,?,-1,0,0,?,0,0,0,0,0,0,0,0,'')",
                       (base + i, base + i, deck_id, now, i + 1))
        db.commit()
        db.close()
        part = out_path + ".part"
        with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(db_path, "collection.anki2")
            z.writestr("media", json.dumps({str(i): name for i, name in enumerate(media_files)}))
            for i, name in enumerate(media_files):
                z.write(os.path.join(media_dir, name), str(i), compress_type=zipfile.ZIP_STORED)
        os.replace(part, out_path)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ───────────────────────────── deck generation job ─────────────────────────────
def slugify(s, fallback="deck"):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")
    return s[:60] or fallback + hashlib.sha1(fallback.encode()).hexdigest()[:6]


def stamp(ms):
    h, rem = divmod(int(ms), 3600000)
    m, rem = divmod(rem, 60000)
    return "%d.%02d.%02d.%03d" % (h, m, rem // 1000, rem % 1000)


def clip_span(start_ms, end_ms, pad_before, pad_after):
    """Where a line's audio clip starts and ends. Padding may be negative, which trims the clip;
    trimming that would leave under a fifth of a second falls back to the subtitle's own times."""
    st, en = max(0, start_ms - pad_before), end_ms + pad_after
    return (st, en) if en - st >= 200 else (max(0, start_ms), end_ms)


def clip_cmd(video, start_ms, end_ms, track, bitrate, out):
    return [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-ss", "%.3f" % (start_ms / 1000),
            "-t", "%.3f" % ((end_ms - start_ms) / 1000), "-i", video, "-vn", "-sn", "-map", "0:a:%d" % track,
            "-ac", "2", "-c:a", "libmp3lame", "-b:a", "%dk" % bitrate, "-f", "mp3", out]


def shot_cmd(video, at_ms, width, out, piped=False):
    cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-ss", "%.3f" % (at_ms / 1000), "-i", video,
           "-an", "-sn", "-frames:v", "1", "-vf", "scale=%d:-2" % width, "-q:v", "5"]
    return cmd + (["-f", "image2pipe", "-c:v", "mjpeg", out] if piped else ["-f", "image2", "-update", "1", out])


def set_job(**kw):
    with JOB_LOCK:
        JOB.update(kw)


def generate(req):
    video, pr = STATE["video"], STATE["probe"]
    work = tempfile.mkdtemp(prefix="trailblazer_media_")
    try:
        deck = (req.get("deck") or pr["stem"]).strip()
        episode = (req.get("episode") or pr["stem"]).strip()
        slug = slugify(deck + "_" + episode, episode)
        want_audio = bool(req.get("audio", True)) and bool(pr["audio"])
        want_shot = bool(req.get("snapshot", True)) and pr["has_video"]
        pad_b, pad_a = int(req.get("pad_before", 0)), int(req.get("pad_after", 400))
        width, bitrate = int(req.get("width", 480)), int(req.get("bitrate", 96))
        track, lines = int(req.get("track", 0)), req["lines"]
        dur_ms = pr["duration"] * 1000 if pr["duration"] else None
        set_job(state="running", done=0, total=len(lines), message="Cutting clips…", path="", failures=0)

        def make(ln):
            if CANCEL.is_set():
                return None
            seq = stamp(ln["start"])
            base = "trailblazer_%s_%s" % (slug, seq)
            audio = shot = ""
            if want_audio:
                st, en = clip_span(ln["start"], ln["end"], pad_b, pad_a)
                if dur_ms:
                    en = min(en, dur_ms)
                name = base + ".mp3"
                r = run(clip_cmd(video, st, en, track, bitrate, os.path.join(work, name)))
                if r.returncode == 0 and os.path.getsize(os.path.join(work, name)) > 0:
                    audio = name
            if want_shot:
                name = base + ".jpg"
                r = run(shot_cmd(video, (ln["start"] + ln["end"]) / 2, width, os.path.join(work, name)))
                if r.returncode == 0 and os.path.exists(os.path.join(work, name)):
                    shot = name
            failed = (want_audio and not audio) or (want_shot and not shot)
            with JOB_LOCK:
                JOB["done"] += 1
                JOB["failures"] += 1 if failed else 0
            return {"seq": seq, "audio": audio, "shot": shot}

        workers = max(1, min(4, os.cpu_count() or 2))
        with concurrent.futures.ThreadPoolExecutor(workers) as pool:
            results = list(pool.map(make, lines))
        if CANCEL.is_set():
            set_job(state="cancelled", message="Cancelled.")
            return
        set_job(message="Packing the deck…")
        notes, media = [], []
        for ln, res in zip(lines, results):
            media += [m for m in (res["audio"], res["shot"]) if m]
            seq = "%s_%s" % (episode, res["seq"])
            guid = base64.urlsafe_b64encode(hashlib.sha1(("%s|%s|%d" % (deck, episode, ln["start"]))
                                                         .encode("utf-8")).digest()[:9]).decode()
            notes.append({"guid": guid, "tags": ["Trailblazer", slugify(episode, "episode")],
                          "fields": [html.escape(seq), html.escape(ln["text"]), html.escape(ln.get("trans") or ""),
                                     "[sound:%s]" % res["audio"] if res["audio"] else "",
                                     '<img src="%s">' % res["shot"] if res["shot"] else "",
                                     html.escape("%s · %s" % (episode, res["seq"].rsplit(".", 1)[0].replace(".", ":"))),
                                     ""] + [""] * 6})
        outdir = os.path.expanduser(req.get("outdir") or pr["folder"])
        if not (os.path.isdir(outdir) and os.access(outdir, os.W_OK)):
            outdir = os.path.join(os.path.expanduser("~"), "Downloads")
            os.makedirs(outdir, exist_ok=True)
        fname = re.sub(r'[\\/:*?"<>|]+', "-", deck.replace("::", " - ") if deck == episode
                       else "%s - %s" % (deck.replace("::", " - "), episode)).strip() + ".apkg"
        out = os.path.join(outdir, fname)
        write_apkg(out, deck, notes, work, media)
        set_job(state="done", path=out, message="%d cards written." % len(notes))
    except Exception as e:                                # surfaced in the interface
        set_job(state="error", message=str(e) or e.__class__.__name__)
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ───────────────────────────── file browser ─────────────────────────────
def list_dir(path, kind):
    home = os.path.expanduser("~")
    path = os.path.abspath(os.path.expanduser(path or home))
    if not os.path.isdir(path):
        path = home
    exts = {"video": MEDIA_EXT, "subs": SUB_EXT}.get(kind, set())
    dirs, files = [], []
    try:
        for e in os.scandir(path):
            if e.name.startswith("."):
                continue
            try:
                if e.is_dir():
                    dirs.append(e.name)
                elif os.path.splitext(e.name)[1].lower() in exts:
                    files.append(e.name)
            except OSError:
                pass
    except OSError as err:
        raise ValueError("Can't open that folder: %s" % err.strerror)
    places = [{"name": "Home", "path": home}]
    for n in ("Desktop", "Downloads", "Movies", "Videos", "Documents"):
        if os.path.isdir(os.path.join(home, n)):
            places.append({"name": n, "path": os.path.join(home, n)})
    if sys.platform == "darwin" and os.path.isdir("/Volumes"):
        places.append({"name": "Drives", "path": "/Volumes"})
    if os.name == "nt":
        places += [{"name": d + ":", "path": d + ":\\"} for d in string.ascii_uppercase if os.path.isdir(d + ":\\")]
    key = lambda s: s.lower()
    return {"path": path, "parent": os.path.dirname(path) or path, "sep": os.sep,
            "dirs": sorted(dirs, key=key), "files": sorted(files, key=key), "places": places}


# ───────────────────────────── web server ─────────────────────────────
class Handler(BaseHTTPRequestHandler):
    server_version = APP

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _ok(self, q):
        host = (self.headers.get("Host") or "").split(":")[0]
        if host not in ("127.0.0.1", "localhost"):
            return False
        return secrets.compare_digest(self.headers.get("X-Token") or (q.get("t") or [""])[0], TOKEN)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/":
            return self._send(200, PAGE.replace("__TOKEN__", TOKEN), "text/html; charset=utf-8")
        if not u.path.startswith("/api/") or not self._ok(q):
            return self._send(403, {"error": "Forbidden"})
        g = lambda k, d="": (q.get(k) or [d])[0]
        try:
            if u.path == "/api/status":
                return self._send(200, {"ffmpeg": bool(FFMPEG and FFPROBE), "version": VERSION,
                                        "platform": sys.platform})
            if u.path == "/api/ls":
                return self._send(200, list_dir(g("path"), g("kind")))
            if u.path == "/api/job":
                with JOB_LOCK:
                    return self._send(200, dict(JOB))
            if u.path == "/api/preview/audio" and STATE["video"]:
                r = run(clip_cmd(STATE["video"], int(g("start", "0")), int(g("end", "0")), int(g("track", "0")),
                                 96, "pipe:1"), timeout=60)
                return self._send(200 if r.stdout else 500, r.stdout, "audio/mpeg")
            if u.path == "/api/preview/image" and STATE["video"]:
                r = run(shot_cmd(STATE["video"], int(g("ms", "0")), 480, "pipe:1", piped=True), timeout=60)
                return self._send(200 if r.stdout else 500, r.stdout, "image/jpeg")
            if u.path == "/api/download" and JOB["path"] and os.path.isfile(JOB["path"]):
                data = open(JOB["path"], "rb").read()
                name = os.path.basename(JOB["path"]).encode("ascii", "ignore").decode() or "deck.apkg"
                return self._send(200, data, "application/octet-stream",
                                  {"Content-Disposition": 'attachment; filename="%s"' % name.replace('"', "")})
            self._send(404, {"error": "Not found"})
        except Exception as e:
            self._send(400, {"error": str(e) or e.__class__.__name__})

    def do_POST(self):
        u = urlparse(self.path)
        if not u.path.startswith("/api/") or not self._ok({}):
            return self._send(403, {"error": "Forbidden"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            req = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            if u.path == "/api/probe":
                path = os.path.abspath(os.path.expanduser(req["video"]))
                if not os.path.isfile(path):
                    raise ValueError("That file doesn't exist.")
                STATE["probe"], STATE["video"] = probe(path), path
                return self._send(200, dict(STATE["probe"], video=path))
            if u.path == "/api/load":
                if not STATE["video"]:
                    raise ValueError("Choose a video first.")
                sfx = bool(req.get("strip_sfx", True))
                target = tidy(load_source(STATE["video"], req["target"]), int(req.get("shift", 0)), sfx)
                if req.get("join", True):
                    target = join_split(target)
                if not target:
                    raise ValueError("No subtitle lines found in that source.")
                trans = tidy(load_source(STATE["video"], req["trans"]), int(req.get("trans_shift", 0)), sfx) \
                    if req.get("trans") else []
                return self._send(200, {"lines": pair(target, trans)})
            if u.path == "/api/generate":
                if JOB["state"] == "running":
                    raise ValueError("A deck is already being created.")
                if not req.get("lines"):
                    raise ValueError("No lines selected.")
                CANCEL.clear()
                set_job(state="running", done=0, total=len(req["lines"]), message="Starting…", path="", failures=0)
                threading.Thread(target=generate, args=(req,), daemon=True).start()
                return self._send(200, {"ok": True})
            if u.path == "/api/cancel":
                CANCEL.set()
                return self._send(200, {"ok": True})
            if u.path == "/api/reveal" and JOB["path"]:
                folder = os.path.dirname(JOB["path"])
                if sys.platform == "darwin":
                    subprocess.Popen(["open", "-R", JOB["path"]])
                elif os.name == "nt":
                    subprocess.Popen(["explorer", "/select,", JOB["path"]])
                else:
                    subprocess.Popen(["xdg-open", folder])
                return self._send(200, {"ok": True})
            if u.path == "/api/quit":
                self._send(200, {"ok": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            self._send(404, {"error": "Not found"})
        except Exception as e:
            self._send(400, {"error": str(e) or e.__class__.__name__})


# ───────────────────────────── interface ─────────────────────────────
PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>PathToFluent Trailblazer</title>
<style>
:root{--bg:#f4f4f1;--card:#fff;--ink:#1d1d1f;--mute:#6b6b70;--line:#e2e2dd;--acc:#2f6f5e;--acc2:#e7f1ee;--bad:#b3261e}
@media(prefers-color-scheme:dark){:root{--bg:#161617;--card:#212123;--ink:#ececec;--mute:#9a9aa0;--line:#333336;--acc:#6fc3ab;--acc2:#23332f;--bad:#ff8a80}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
header{display:flex;align-items:center;gap:12px;padding:18px 28px}header h1{font-size:20px;margin:0;letter-spacing:-.01em}
header span{color:var(--mute);font-size:13px;flex:1}main{max-width:1060px;margin:0 auto;padding:0 20px 80px}
section{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:22px 24px;margin-bottom:18px}
section h2{margin:0 0 4px;font-size:16px}section h2 b{display:inline-grid;place-items:center;width:24px;height:24px;border-radius:50%;background:var(--acc);color:var(--card);font-size:13px;margin-right:8px}
.hint{color:var(--mute);font-size:13px;margin:0 0 16px}.row{display:flex;gap:10px;align-items:center;margin:10px 0;flex-wrap:wrap}
label{font-size:13px;color:var(--mute);min-width:150px}input[type=text],input[type=number],select{font:inherit;color:inherit;background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:8px 10px}
input[type=text],select{flex:1;min-width:200px}input[type=number]{width:90px}
button{font:inherit;border-radius:8px;border:1px solid var(--line);background:var(--card);color:inherit;padding:8px 14px;cursor:pointer}
button:hover{border-color:var(--acc)}button.primary{background:var(--acc);border-color:var(--acc);color:var(--card);font-weight:600}
button:disabled{opacity:.45;cursor:default}details{margin-top:8px}summary{cursor:pointer;color:var(--mute);font-size:13px}
.err{color:var(--bad);font-size:13px;margin-top:8px;white-space:pre-wrap}.hide{display:none!important}
.bar{display:flex;gap:10px;align-items:center;margin-bottom:10px;flex-wrap:wrap}.bar .count{color:var(--mute);font-size:13px;flex:1;text-align:right}
.review{display:grid;grid-template-columns:1fr 260px;gap:16px}@media(max-width:800px){.review{grid-template-columns:1fr}}
.tablewrap{max-height:520px;overflow:auto;border:1px solid var(--line);border-radius:10px}
table{border-collapse:collapse;width:100%;font-size:14px}th{position:sticky;top:0;background:var(--card);text-align:left;font-size:12px;color:var(--mute);font-weight:500;padding:8px;border-bottom:1px solid var(--line);z-index:1}
td{padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}tr.off td{opacity:.4}tr.cur td{background:var(--acc2)}
td.tm{font-variant-numeric:tabular-nums;color:var(--mute);white-space:nowrap}td[contenteditable]{outline:none;border-radius:4px}td[contenteditable]:focus{background:var(--bg)}
.play{padding:2px 9px;border-radius:999px}.side{position:sticky;top:10px;align-self:start}.side img{width:100%;border-radius:10px;background:var(--bg);min-height:120px;display:block}
.side p{font-size:13px;color:var(--mute)}progress{width:100%;height:10px;accent-color:var(--acc)}
.done{background:var(--acc2);border-radius:10px;padding:14px 16px;margin-top:14px}
dialog{border:1px solid var(--line);border-radius:14px;background:var(--card);color:var(--ink);padding:0;width:min(640px,94vw)}
dialog::backdrop{background:#0006}.dlg{padding:18px 20px}.places{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0}
.places button{padding:4px 10px;font-size:13px;border-radius:999px}.path{font-size:12px;color:var(--mute);word-break:break-all}
.list{height:340px;overflow:auto;border:1px solid var(--line);border-radius:10px;margin:10px 0}
.list div{padding:7px 12px;cursor:pointer;border-bottom:1px solid var(--line);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.list div:hover{background:var(--acc2)}.list .d{font-weight:500}.list .e{color:var(--mute);cursor:default}
</style></head><body>
<header><h1>PathToFluent Trailblazer</h1><span>Video + subtitles → Anki cards</span><button id="quit">Quit</button></header>
<main>
<section id="noff" class="hide"><h2>ffmpeg is needed</h2><p class="hint">Trailblazer uses the free tool ffmpeg to cut audio and grab snapshots, and it isn't installed yet.<br>
macOS: install Homebrew from brew.sh, then run <code>brew install ffmpeg</code> in Terminal. Windows: <code>winget install ffmpeg</code>. Linux: install <code>ffmpeg</code> with your package manager. Then restart Trailblazer.</p></section>

<section id="s1"><h2><b>1</b>Choose your files</h2><p class="hint">Pick an episode or film, then the subtitles in the language you're learning.</p>
<div class="row"><label>Video or audio file</label><input type="text" id="video" placeholder="Click Browse, or paste a full path" spellcheck="false"><button id="bvideo">Browse…</button></div>
<div class="row"><label>Subtitles (language you're learning)</label><select id="target" disabled><option value="">Choose a video first</option></select></div>
<div class="row"><label>Translation subtitles (optional)</label><select id="trans" disabled><option value="">None</option></select></div>
<div class="row hide" id="trackrow"><label>Audio track</label><select id="track"></select></div>
<details><summary>Timing and clean-up options</summary>
<div class="row"><label>Shift subtitles by</label><input type="number" id="shift" value="0" step="50"> ms <span class="hint" style="margin:0">(positive = later; use if the text is out of sync with the speech)</span></div>
<div class="row"><label>Shift translation by</label><input type="number" id="tshift" value="0" step="50"> ms</div>
<div class="row"><label></label><input type="checkbox" id="sfx" checked><span>Drop sound-effect, speaker and music captions like [door slams], (MUJER), and sung lines marked ♪</span></div>
<div class="row"><label></label><input type="checkbox" id="join" checked><span>Join a sentence that the subtitles split across two or three lines</span></div></details>
<div class="row"><button class="primary" id="load" disabled>Load subtitle lines</button><span id="loadmsg" class="hint" style="margin:0"></span></div>
<div class="err" id="err1"></div></section>

<section id="s2" class="hide"><h2><b>2</b>Review the lines</h2><p class="hint">Untick anything you don't want as a card. Press ▶ to hear a line and see its snapshot. Click any text to edit it.</p>
<div class="bar"><button id="all">Select all</button><button id="none">Select none</button><input type="text" id="filter" placeholder="Filter lines…" style="max-width:240px"><span class="count" id="count"></span></div>
<div class="row"><label>Extra audio before / after</label><input type="number" id="padb" value="0" step="50"> / <input type="number" id="pada" value="400" step="50"> ms <span class="hint" style="margin:0">▶ uses these, and so does the deck. A negative number trims: try -200 before if you hear the end of the previous line.</span></div>
<div class="review"><div class="tablewrap"><table><thead><tr><th></th><th></th><th>Time</th><th>Sentence</th><th id="thtr">Translation</th></tr></thead><tbody id="rows"></tbody></table></div>
<div class="side"><img id="shot" alt=""><p id="sidetxt">Press ▶ on a line to preview it.</p></div></div></section>

<section id="s3" class="hide"><h2><b>3</b>Create the deck</h2><p class="hint">You'll get one .apkg file. Double-click it and Anki imports the cards, audio and images.</p>
<div class="row"><label>Deck name</label><input type="text" id="deck"><span class="hint" style="margin:0">Use :: for sub-decks, e.g. Spanish::Series</span></div>
<div class="row"><label>Episode label</label><input type="text" id="episode"></div>
<div class="row"><label>Save to folder</label><input type="text" id="outdir" spellcheck="false"><button id="bout">Browse…</button></div>
<div class="row"><label>Include</label><input type="checkbox" id="waudio" checked><span>Audio clip</span>&nbsp;&nbsp;<input type="checkbox" id="wshot" checked><span>Snapshot</span></div>
<details><summary>Audio and image options</summary>
<div class="row"><label>Audio quality</label><select id="bitrate" style="flex:0"><option value="64">Small (64 kbps)</option><option value="96" selected>Normal (96 kbps)</option><option value="128">High (128 kbps)</option></select></div>
<div class="row"><label>Snapshot width</label><input type="number" id="width" value="480" min="160" max="1920" step="40"> px</div></details>
<div class="row"><button class="primary" id="go">Create deck</button><button id="cancel" class="hide">Cancel</button></div>
<div id="prog" class="hide"><progress id="pbar" value="0" max="1"></progress><p class="hint" id="pmsg"></p></div>
<div class="err" id="err3"></div>
<div class="done hide" id="done"><b id="donemsg"></b><div class="path" id="donepath"></div><div class="row"><button id="reveal">Show in folder</button><button id="dl">Download a copy</button></div></div></section>
</main>

<dialog id="fb"><div class="dlg"><b id="fbtitle">Choose a file</b><div class="places" id="fbplaces"></div><div class="path" id="fbpath"></div>
<div class="list" id="fblist"></div><div class="row" style="justify-content:flex-end"><button id="fbpick" class="primary hide">Use this folder</button><button id="fbclose">Cancel</button></div></div></dialog>

<script>
const T="__TOKEN__",$=s=>document.querySelector(s),S={lines:[],probe:null,last:-1};
const esc=s=>String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
async function api(p,body){const r=await fetch(p,{method:body?"POST":"GET",headers:{"X-Token":T,"Content-Type":"application/json"},body:body?JSON.stringify(body):undefined});
  const j=await r.json().catch(()=>({error:r.statusText}));if(!r.ok)throw new Error(j.error||"Something went wrong");return j}
const fmt=ms=>{const s=Math.floor(ms/1000),h=Math.floor(s/3600),m=Math.floor(s%3600/60);return (h?h+":":"")+String(m).padStart(h?2:1,"0")+":"+String(s%60).padStart(2,"0")};
const base=p=>p.split(/[\\/]/).pop();

// ── file browser ──
let fbMode="video",fbDone=null;
async function browse(mode,start,done){fbMode=mode;fbDone=done;$("#fbtitle").textContent=mode=="dir"?"Choose a folder":mode=="subs"?"Choose a subtitle file":"Choose a video or audio file";
  $("#fbpick").classList.toggle("hide",mode!="dir");$("#fb").showModal();await ls(start||localStorage.sdDir||"")}
async function ls(path){let d;try{d=await api("/api/ls?kind="+fbMode+"&path="+encodeURIComponent(path))}catch(e){$("#fblist").innerHTML='<div class="e">'+esc(e.message)+"</div>";return}
  S.fb=d;$("#fbpath").textContent=d.path;$("#fbplaces").innerHTML="";
  d.places.forEach(p=>{const b=document.createElement("button");b.textContent=p.name;b.onclick=()=>ls(p.path);$("#fbplaces").appendChild(b)});
  const L=$("#fblist");L.innerHTML="";const add=(cls,txt,fn)=>{const e=document.createElement("div");e.className=cls;e.textContent=txt;if(fn)e.onclick=fn;L.appendChild(e)};
  if(d.parent!=d.path)add("d","↑  Up one folder",()=>ls(d.parent));
  const join=n=>d.path+(d.path.endsWith(d.sep)?"":d.sep)+n;
  d.dirs.forEach(n=>add("d","📁  "+n,()=>ls(join(n))));
  d.files.forEach(n=>add("f",n,()=>{localStorage.sdDir=d.path;$("#fb").close();fbDone(join(n))}));
  if(!d.dirs.length&&!d.files.length)add("e",fbMode=="dir"?"No sub-folders here":"No matching files in this folder")}
$("#fbclose").onclick=()=>$("#fb").close();
$("#fbpick").onclick=()=>{$("#fb").close();fbDone(S.fb.path)};

// ── step 1 ──
function fillSubs(sel,first){const p=S.probe,keep=sel.value;sel.innerHTML="";const o=(v,t,dis)=>{const e=document.createElement("option");e.value=v;e.textContent=t;if(dis)e.disabled=true;sel.appendChild(e)};
  o("",first);p.sidecars.forEach(f=>o("file:"+f,"File: "+base(f)));(S.extra||[]).forEach(f=>o("file:"+f,"File: "+base(f)));
  p.subs.forEach(s=>o("emb:"+s.n,"Inside the video: "+s.label+(s.text?"":" (image-based, can't be used)"),!s.text));
  o("browse","Browse for a subtitle file…");sel.disabled=false;if([...sel.options].some(x=>x.value==keep))sel.value=keep}
async function setVideo(path){$("#err1").textContent="";$("#video").value=path;if(!path)return;$("#loadmsg").textContent="Reading file…";
  try{S.probe=await api("/api/probe",{video:path})}catch(e){$("#err1").textContent=e.message;$("#loadmsg").textContent="";return}
  const p=S.probe;S.extra=[];$("#video").value=p.video;$("#loadmsg").textContent="";fillSubs($("#target"),"Choose subtitles…");fillSubs($("#trans"),"None");
  const first=[...$("#target").options].find(o=>o.value&&o.value!="browse"&&!o.disabled);if(first&&p.sidecars.length+p.subs.filter(s=>s.text).length==1)$("#target").value=first.value;
  $("#track").innerHTML=p.audio.map(a=>`<option value="${a.n}">${esc(a.label)} (${esc(a.codec)})</option>`).join("");$("#trackrow").classList.toggle("hide",p.audio.length<2);
  $("#deck").value=p.stem;$("#episode").value=p.stem;$("#outdir").value=p.folder;
  $("#wshot").checked=p.has_video;$("#wshot").disabled=!p.has_video;$("#waudio").checked=p.audio.length>0;$("#waudio").disabled=!p.audio.length;
  $("#s2").classList.add("hide");$("#s3").classList.add("hide");ready()}
function ready(){$("#load").disabled=!(S.probe&&$("#target").value&&$("#target").value!="browse")}
$("#bvideo").onclick=()=>browse("video","",setVideo);
$("#video").onchange=e=>setVideo(e.target.value.trim().replace(/^["']|["']$/g,""));
["target","trans"].forEach(id=>$("#"+id).onchange=e=>{const sel=e.target;if(sel.value=="browse"){sel.value="";browse("subs",S.probe.folder,f=>{S.extra.push(f);const a=$("#target").value,b=$("#trans").value;
  fillSubs($("#target"),"Choose subtitles…");fillSubs($("#trans"),"None");$("#target").value=a;$("#trans").value=b;sel.value="file:"+f;ready()})}ready()});
$("#load").onclick=async()=>{$("#err1").textContent="";$("#load").disabled=true;$("#loadmsg").textContent="Reading subtitles… (embedded tracks can take a minute)";
  try{const tr=$("#trans").value;const r=await api("/api/load",{target:$("#target").value,trans:tr&&tr!="browse"?tr:null,shift:+$("#shift").value||0,trans_shift:+$("#tshift").value||0,strip_sfx:$("#sfx").checked,join:$("#join").checked});
    S.lines=r.lines.map(l=>Object.assign(l,{on:true}));S.hasTr=S.lines.some(l=>l.trans);$("#filter").value="";render();
    $("#s2").classList.remove("hide");$("#s3").classList.remove("hide");$("#done").classList.add("hide");$("#s2").scrollIntoView({behavior:"smooth"})}
  catch(e){$("#err1").textContent=e.message}$("#loadmsg").textContent="";ready()};

// ── step 2 ──
function render(){const q=$("#filter").value.toLowerCase(),tb=$("#rows"),f=document.createDocumentFragment();tb.innerHTML="";$("#thtr").classList.toggle("hide",!S.hasTr);
  S.lines.forEach((l,i)=>{if(q&&!(l.text.toLowerCase().includes(q)||(l.trans||"").toLowerCase().includes(q)))return;
    const tr=document.createElement("tr");tr.dataset.i=i;if(!l.on)tr.className="off";
    tr.innerHTML=`<td><input type="checkbox" ${l.on?"checked":""}></td><td><button class="play" title="Play this line">▶</button></td><td class="tm">${fmt(l.start)}</td><td class="tx" contenteditable>${esc(l.text)}</td>`+(S.hasTr?`<td class="tr2" contenteditable>${esc(l.trans||"")}</td>`:"");
    f.appendChild(tr)});tb.appendChild(f);count()}
function count(){const on=S.lines.filter(l=>l.on),secs=on.reduce((a,l)=>a+(l.end-l.start),0)/1000;
  $("#count").textContent=`${on.length} of ${S.lines.length} lines selected · ${Math.round(secs/60)} min of audio`;$("#go").disabled=!on.length}
let player=null;
$("#rows").addEventListener("click",e=>{const tr=e.target.closest("tr");if(!tr)return;const i=+tr.dataset.i,l=S.lines[i];
  if(e.target.type=="checkbox"){const on=e.target.checked;let a=i,b=i;if(e.shiftKey&&S.last>=0){a=Math.min(i,S.last);b=Math.max(i,S.last)}
    document.querySelectorAll("#rows tr").forEach(r=>{const k=+r.dataset.i;if(k>=a&&k<=b){S.lines[k].on=on;r.className=on?"":"off";r.querySelector("input").checked=on}});S.last=i;count()}
  else if(e.target.classList.contains("play")){document.querySelectorAll("#rows tr.cur").forEach(r=>r.classList.remove("cur"));tr.classList.add("cur");
    const pb=+$("#padb").value||0,pa=+$("#pada").value||0;let a0=Math.max(0,l.start-pb),a1=l.end+pa;if(a1-a0<200){a0=Math.max(0,l.start);a1=l.end}if(player)player.pause();
    if(S.probe.audio.length){player=new Audio(`/api/preview/audio?start=${a0}&end=${a1}&track=${$("#track").value||0}&t=${T}`);player.play().catch(()=>{})}
    if(S.probe.has_video)$("#shot").src=`/api/preview/image?ms=${Math.round((l.start+l.end)/2)}&t=${T}`;$("#sidetxt").textContent=l.text}});
$("#rows").addEventListener("input",e=>{const tr=e.target.closest("tr");if(!tr)return;const l=S.lines[+tr.dataset.i],v=e.target.textContent.replace(/\s+/g," ").trim();
  if(e.target.classList.contains("tx"))l.text=v;else if(e.target.classList.contains("tr2"))l.trans=v});
const setAll=on=>{document.querySelectorAll("#rows tr").forEach(r=>{S.lines[+r.dataset.i].on=on;r.className=on?"":"off";r.querySelector("input").checked=on});count()};
$("#all").onclick=()=>setAll(true);$("#none").onclick=()=>setAll(false);$("#filter").oninput=render;

// ── step 3 ──
$("#bout").onclick=()=>browse("dir",$("#outdir").value,p=>$("#outdir").value=p);
$("#go").onclick=async()=>{$("#err3").textContent="";$("#done").classList.add("hide");
  const lines=S.lines.filter(l=>l.on&&l.text).map(l=>({start:l.start,end:l.end,text:l.text,trans:l.trans||""}));
  try{await api("/api/generate",{lines,deck:$("#deck").value,episode:$("#episode").value,outdir:$("#outdir").value,audio:$("#waudio").checked,snapshot:$("#wshot").checked,
    pad_before:+$("#padb").value||0,pad_after:+$("#pada").value||0,bitrate:+$("#bitrate").value,width:+$("#width").value||480,track:+$("#track").value||0})}
  catch(e){$("#err3").textContent=e.message;return}
  $("#go").disabled=true;$("#cancel").classList.remove("hide");$("#prog").classList.remove("hide");poll()};
async function poll(){let j;try{j=await api("/api/job")}catch(e){setTimeout(poll,1000);return}
  $("#pbar").max=j.total||1;$("#pbar").value=j.done;$("#pmsg").textContent=j.state=="running"?`${j.message} ${j.done} of ${j.total}`:j.message;
  if(j.state=="running"){setTimeout(poll,500);return}
  $("#go").disabled=false;$("#cancel").classList.add("hide");$("#prog").classList.add("hide");
  if(j.state=="error")$("#err3").textContent="Couldn't create the deck: "+j.message;
  if(j.state=="done"){$("#donemsg").textContent="Deck ready — "+j.message+(j.failures?` (${j.failures} lines are missing audio or a snapshot.)`:"");$("#donepath").textContent=j.path;$("#done").classList.remove("hide")}}
$("#cancel").onclick=()=>api("/api/cancel",{x:1});
$("#reveal").onclick=()=>api("/api/reveal",{x:1}).catch(()=>{});
$("#dl").onclick=()=>{location.href="/api/download?t="+T};
$("#quit").onclick=async()=>{if(!confirm("Quit Trailblazer?"))return;await api("/api/quit",{x:1}).catch(()=>{});document.body.innerHTML='<p style="padding:40px">Trailblazer has stopped. You can close this tab.</p>'};
api("/api/status").then(s=>{if(!s.ffmpeg){$("#noff").classList.remove("hide");$("#s1").classList.add("hide")}});
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser(description="Trailblazer - video + subtitles to Anki cards")
    ap.add_argument("--port", type=int, default=8777)
    ap.add_argument("--no-browser", action="store_true", help="don't open the browser automatically")
    args = ap.parse_args()
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError:
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    url = "http://127.0.0.1:%d/" % httpd.server_address[1]
    print("%s %s is running at %s\nLeave this window open while you use it. Press Ctrl+C to quit." % (APP, VERSION, url))
    if not (FFMPEG and FFPROBE):
        print("Note: ffmpeg was not found. On macOS, install it with:  brew install ffmpeg")
    if not args.no_browser:
        threading.Timer(0.4, webbrowser.open, args=(url,)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    print("\n%s stopped." % APP)


if __name__ == "__main__":
    main()
