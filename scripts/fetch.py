#!/usr/bin/env python3
"""Unduh video + transkrip word-level dari YouTube.

  uv run fetch.py <url> <workdir> [--lang auto|id|en] [--height 1080]

Menghasilkan di <workdir>:
  source.mp4      video
  words.json      [{"t": detik, "w": kata}, ...]  <- timing per kata
  transcript.txt  transkrip terbaca, blok 20 detik, ber-timestamp
  meta.json       id, judul, channel, durasi
"""
import argparse, json, os, subprocess, sys, shutil

def sh(cmd, **kw):
    return subprocess.run(cmd, text=True, capture_output=True, **kw)

def need_ytdlp():
    if shutil.which("yt-dlp"):
        return "yt-dlp"
    local = os.path.expanduser("~/.local/bin/yt-dlp")
    if os.path.exists(local):
        return local
    print("yt-dlp tidak ada, memasang lewat uv...", file=sys.stderr)
    subprocess.run(["uv", "tool", "install", "yt-dlp"], check=True)
    return local

def pick_lang(ytdlp, url, want):
    if want != "auto":
        return want
    r = sh([ytdlp, "--skip-download", "--print", "%(language)s", url])
    lang = (r.stdout or "").strip().splitlines()
    if lang and lang[-1] not in ("NA", ""):
        return lang[-1].split("-")[0]
    subs = sh([ytdlp, "--list-subs", url]).stdout
    for cand in ("id", "en"):
        if any(l.startswith(cand + " ") for l in subs.splitlines()):
            return cand
    return "en"

def parse_json3(path):
    d = json.load(open(path))
    words = []
    for ev in d.get("events", []):
        if "segs" not in ev:
            continue
        t0 = ev.get("tStartMs", 0)
        for s in ev["segs"]:
            txt = s.get("utf8", "")
            if not txt.strip():
                continue
            words.append({"t": round((t0 + s.get("tOffsetMs", 0)) / 1000.0, 2),
                          "w": txt.strip()})
    words.sort(key=lambda x: x["t"])
    return words

def write_transcript(words, path, block=20):
    def hms(t):
        return f"{int(t//60):02d}:{int(t%60):02d}"
    out, buf, start = [], [], None
    for w in words:
        if start is None:
            start = w["t"]
        if w["t"] - start >= block:
            out.append(f"[{hms(start)}] " + " ".join(buf))
            buf, start = [], w["t"]
        buf.append(w["w"])
    if buf:
        out.append(f"[{hms(start)}] " + " ".join(buf))
    open(path, "w").write("\n".join(out))
    return len(out)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url"); ap.add_argument("workdir")
    ap.add_argument("--lang", default="auto")
    ap.add_argument("--height", default="1080")
    a = ap.parse_args()

    W = os.path.abspath(a.workdir); os.makedirs(W, exist_ok=True)
    yt = need_ytdlp()

    if not shutil.which("deno"):
        print("catatan: deno tidak ada — yt-dlp mungkin kehilangan format kualitas tinggi.", file=sys.stderr)
        print("        pasang dengan: brew install deno", file=sys.stderr)

    lang = pick_lang(yt, a.url, a.lang)
    print(f"bahasa caption: {lang}")

    fmt = (f"bv*[height<={a.height}][ext=mp4]+ba[ext=m4a]/b[height<={a.height}]")
    subprocess.run([yt, "-f", fmt, "--write-auto-subs", "--sub-langs", lang,
                    "--sub-format", "json3", "--merge-output-format", "mp4",
                    "--no-progress", "-o", f"{W}/source.%(ext)s", a.url], check=True)

    j3 = f"{W}/source.{lang}.json3"
    if not os.path.exists(j3):
        sys.exit(f"caption {lang} tidak terunduh — cek `yt-dlp --list-subs {a.url}`")

    words = parse_json3(j3)
    json.dump(words, open(f"{W}/words.json", "w"), ensure_ascii=False)
    n = write_transcript(words, f"{W}/transcript.txt")

    meta = sh([yt, "--skip-download", "--print",
               "%(id)s|%(title)s|%(duration)s|%(channel)s", a.url]).stdout.strip().splitlines()
    if meta:
        p = meta[-1].split("|")
        json.dump(dict(zip(["id", "title", "duration", "channel"], p)),
                  open(f"{W}/meta.json", "w"), ensure_ascii=False, indent=1)

    print(f"OK  {len(words)} kata, {n} blok transkrip, durasi {words[-1]['t']:.0f}s")
    print(f"    baca {W}/transcript.txt untuk memilih momen")

main()
