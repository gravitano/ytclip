#!/usr/bin/env python3
"""Render klip vertikal 1080x1920 bersubtitle karaoke dari source.mp4 + words.json.

  uv run --with pillow render.py <workdir> [outdir] [--only 03] [--dry-run] [--fast]

Baca <workdir>/clips.json. --dry-run hanya mencetak teks caption untuk direview
(WAJIB dilakukan dulu: auto-caption YouTube selalu punya salah dengar).

Subtitle dirender sebagai PNG overlay, bukan ASS — ffmpeg Homebrew sering dibuild
tanpa libass/libfreetype sehingga filter `subtitles` dan `drawtext` tidak ada.
"""
import argparse, json, os, re, shutil, subprocess, sys
from PIL import Image, ImageDraw, ImageFont

FONT_PATH = "/System/Library/Fonts/Avenir Next.ttc"
FONT_HEAVY, FONT_DEMI = 8, 2
CANVAS_W, CANVAS_H = 1080, 1920

DEFAULT_STYLE = {
    "head_h": 170,          # tinggi band judul di atas
    "cap_y": 1400,          # posisi atas strip caption
    "cap_h": 380,
    "size": 68,             # ukuran font caption
    "max_w": 960,           # lebar maksimum satu baris (px)
    "max_words": 4,         # kata maksimum satu baris
    "title_size": 54,
    "tag_size": 30,
    "hilite": [255, 214, 10],
    "bg": "0x0B0B0F",
    "tag": "",
}
# filler yang dibuang dari caption (bukan dari audio)
DROP = {"ee", "eh", "e", "ah", "h", "heeh", "he", "hm", "hmm", "i", "ck", "oh"}


def norm(w):
    return re.sub(r"[^\w\-.%]", "", w).lower().rstrip(".,?!")


def build_words(clip, words, fixes, drop_extra):
    out = []
    for w in words:
        if not (clip["start"] <= w["t"] < clip["end"]):
            continue
        raw = w["w"]
        if raw.startswith("["):          # [tertawa], [musik], ...
            continue
        n = norm(raw)
        if n in DROP or n in drop_extra:
            continue
        if n in fixes:
            tail = raw[-1] if raw[-1:] in ".,?!" else ""
            raw = fixes[n] + tail
        out.append([round(w["t"] - clip["start"], 2), raw])
    return out


class Caption:
    def __init__(self, st):
        self.st = st
        self.f = ImageFont.truetype(FONT_PATH, st["size"], index=FONT_HEAVY)
        self.ft = ImageFont.truetype(FONT_PATH, st["title_size"], index=FONT_HEAVY)
        self.fg = ImageFont.truetype(FONT_PATH, st["tag_size"], index=FONT_DEMI)
        self.d0 = ImageDraw.Draw(Image.new("RGBA", (10, 10)))

    def w_of(self, t, f=None):
        return self.d0.textbbox((0, 0), t, font=f or self.f, stroke_width=8)[2]

    def group(self, words):
        """Potong per kalimat dulu, baru per lebar — supaya tidak ada baris
        yang diawali ekor kalimat sebelumnya."""
        sents, cur = [], []
        for w in words:
            cur.append(w)
            if w[1].rstrip().endswith((".", "?", "!")):
                sents.append(cur); cur = []
        if cur:
            sents.append(cur)
        lines = []
        for sent in sents:
            cur = []
            for w in sent:
                trial = cur + [w]
                txt = " ".join(x[1] for x in trial).upper()
                if cur and (self.w_of(txt) > self.st["max_w"]
                            or len(trial) > self.st["max_words"]):
                    lines.append(cur); cur = [w]
                else:
                    cur = trial
            if cur:
                lines.append(cur)
        return lines

    def draw_line(self, line, active):
        st = self.st
        img = Image.new("RGBA", (CANVAS_W, st["cap_h"]), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        toks = [w[1].upper() for w in line]
        widths = [self.w_of(t) for t in toks]
        space = self.w_of(" ")
        x = (CANVAS_W - (sum(widths) + space * (len(toks) - 1))) // 2
        y = st["cap_h"] // 2 - st["size"] // 2
        hil = tuple(st["hilite"]) + (255,)
        for i, t in enumerate(toks):
            d.text((x + 3, y + 5), t, font=self.f, fill=(0, 0, 0, 150),
                   stroke_width=8, stroke_fill=(0, 0, 0, 150))
            d.text((x, y), t, font=self.f,
                   fill=hil if i == active else (255, 255, 255, 255),
                   stroke_width=8, stroke_fill=(0, 0, 0, 255))
            x += widths[i] + space
        return img

    def draw_header(self, title):
        st = self.st
        img = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        y = 44
        for ln in title.split("\n"):
            w = d.textbbox((0, 0), ln, font=self.ft, stroke_width=6)[2]
            d.text(((CANVAS_W - w) // 2, y), ln, font=self.ft,
                   fill=(255, 255, 255, 255), stroke_width=6, stroke_fill=(0, 0, 0, 255))
            y += st["title_size"] + 8
        if st["tag"]:
            w = d.textbbox((0, 0), st["tag"], font=self.fg, stroke_width=4)[2]
            d.text(((CANVAS_W - w) // 2, CANVAS_H - 68), st["tag"], font=self.fg,
                   fill=(255, 255, 255, 200), stroke_width=4, stroke_fill=(0, 0, 0, 255))
        return img


def _switch_expr(shots, values):
    """Ekspresi ffmpeg yang berganti nilai tepat di batas shot.

    Perpindahan crop SENGAJA dijatuhkan pada potongan yang sudah ada di
    sumber. Di titik itu gambarnya memang berganti total, jadi lompatan
    bingkai tidak terlihat sebagai kesalahan — berbeda dengan memindahkan
    bingkai di tengah shot, yang selalu terbaca sebagai glitch."""
    expr = str(values[-1])
    for i in range(len(shots) - 2, -1, -1):
        expr = f"if(lt(t,{shots[i]['t1']:.3f}),{values[i]},{expr})"
    return expr


def crop_for(face, src_w, src_h, pw, ph):
    """Crop beraspek panel, di-zoom, dipusatkan ke wajah, lalu dijepit ke tepi frame.
    Penjepitan inilah yang memberi lookroom otomatis: orang di kiri frame akan
    menempel ke kiri panel, jadi ruang pandangnya jatuh ke kanan."""
    zoom = face.get("zoom", 1.35)
    ch = min(src_h, int(src_h / zoom))
    cw = int(ch * pw / ph)
    if cw > src_w:
        cw = src_w; ch = int(cw * ph / pw)
    x = int(face["cx"] - cw / 2)
    y = int(face["cy"] - ch * face.get("headroom", 0.43))
    x = max(0, min(x, src_w - cw))
    y = max(0, min(y, src_h - ch))
    return f"crop={cw}:{ch}:{x}:{y},scale={pw}:{ph},setsar=1"


def filtergraph(clip, st, src_w, src_h):
    head = st["head_h"]
    lay = clip.get("layout", "split")
    if lay == "split":
        ph = (CANVAS_H - head) // 2
        top = crop_for(clip["top"], src_w, src_h, CANVAS_W, ph)
        bot = crop_for(clip["bottom"], src_w, src_h, CANVAS_W, ph)
        base = (f"[0:v]{top}[top];[0:v]{bot}[bot];"
                f"color=c={st['bg']}:s={CANVAS_W}x{CANVAS_H}:d=1[bg];"
                f"[bg][top]overlay=0:{head}[a];[a][bot]overlay=0:{head + ph}[b];")
    elif lay == "track":
        # Satu bingkai tegak yang berpindah mengikuti wajah, berganti tepat
        # di potongan sumber. Untuk sumber multicam, di mana bingkai tetap
        # akan meleset begitu kamera berganti.
        #
        # Tiap shot dapat ukuran crop SENDIRI, dihitung dari tinggi wajah,
        # supaya wajah menempati porsi layar yang sama di semua shot. Tanpa
        # ini, potongan ke wide shot terbaca sebagai zoom-out mendadak:
        # pada sumber ultrawide, wajah di wide shot bisa cuma separuh
        # ukurannya di close-up.
        shots = clip["shots"]
        target = clip.get("face_ratio", 0.45)
        hr = clip.get("headroom", 0.42)
        parts, labels = [], []
        for i, sh in enumerate(shots):
            fh = sh.get("fh") or 0
            ch = int(src_h / clip.get("zoom", 1.0)) if not fh else int(fh / target)
            ch = max(240, min(src_h, ch)) // 2 * 2
            cw = max(120, min(src_w, int(ch * CANVAS_W / CANVAS_H))) // 2 * 2
            x = max(0, min(int(sh["cx"] - cw / 2), src_w - cw))
            y = max(0, min(int(sh["cy"] - ch * hr), src_h - ch))
            t1 = min(sh["t1"], clip["end"] - clip["start"])
            parts.append(
                f"[0:v]trim=start={sh['t0']:.3f}:end={t1:.3f},setpts=PTS-STARTPTS,"
                f"crop={cw}:{ch}:{x}:{y},scale={CANVAS_W}:{CANVAS_H},setsar=1[s{i}];")
            labels.append(f"[s{i}]")
        base = ("".join(parts) +
                "".join(labels) + f"concat=n={len(shots)}:v=1:a=0[b];")
    elif lay == "single":
        one = crop_for(clip["face"], src_w, src_h, CANVAS_W, CANVAS_H)
        base = f"[0:v]{one}[b];"
    else:  # fit — video utuh di tengah, latar blur
        base = (f"[0:v]scale={CANVAS_W}:-2,setsar=1[fg];"
                f"[0:v]scale={CANVAS_W}:{CANVAS_H}:force_original_aspect_ratio=increase,"
                f"crop={CANVAS_W}:{CANVAS_H},gblur=sigma=40[bgv];"
                f"[bgv][fg]overlay=0:(H-h)/2[b];")
    return (base + "[b][1:v]overlay=0:0[c];"
            f"[c][2:v]overlay=0:{st['cap_y']}:eof_action=pass[v]")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workdir"); ap.add_argument("outdir", nargs="?")
    ap.add_argument("--only"); ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--fast", action="store_true")
    a = ap.parse_args()

    W = os.path.abspath(a.workdir)
    OUT = os.path.abspath(a.outdir or f"{W}/out")
    cfg = json.load(open(f"{W}/clips.json"))
    if isinstance(cfg, list):
        cfg = {"clips": cfg}
    st = {**DEFAULT_STYLE, **cfg.get("style", {})}
    fixes = {k.lower(): v for k, v in cfg.get("fixes", {}).items()}
    drop_extra = {x.lower() for x in cfg.get("drop", [])}
    words = json.load(open(f"{W}/words.json"))
    cap = Caption(st)

    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                            "-show_entries", "stream=width,height", "-of", "csv=p=0",
                            f"{W}/source.mp4"], text=True, capture_output=True).stdout
    src_w, src_h = [int(x) for x in probe.strip().split(",")[:2]]

    os.makedirs(OUT, exist_ok=True)
    for clip in cfg["clips"]:
        if a.only and clip["id"] != a.only:
            continue
        cw = build_words(clip, words, fixes, drop_extra)
        dur = clip["end"] - clip["start"]
        if a.dry_run:
            print(f"--- clip{clip['id']}  {clip['start']}→{clip['end']}  ({dur:.1f}s, {len(cw)} kata)")
            print(" ".join(x[1] for x in cw), "\n")
            continue

        tmp = f"{W}/tmp_{clip['id']}"
        shutil.rmtree(tmp, ignore_errors=True); os.makedirs(tmp)
        cap.draw_header(clip.get("title", "")).save(f"{tmp}/header.png")

        lines = cap.group(cw)
        seq, n = [], 0
        for li, line in enumerate(lines):
            for wi, (t, _) in enumerate(line):
                nxt = (line[wi + 1][0] if wi + 1 < len(line)
                       else lines[li + 1][0][0] if li + 1 < len(lines) else dur)
                p = f"{tmp}/w{n:04d}.png"
                cap.draw_line(line, wi).save(p)
                seq.append((p, t, nxt)); n += 1

        blank = f"{tmp}/blank.png"
        Image.new("RGBA", (CANVAS_W, st["cap_h"]), (0, 0, 0, 0)).save(blank)
        entries = ([(blank, seq[0][1])] if seq[0][1] > 0.05 else []) + \
                  [(p, max(0.06, b - t)) for p, t, b in seq]
        with open(f"{tmp}/list.txt", "w") as fh:
            for p, d in entries:
                fh.write(f"file '{p}'\nduration {d:.3f}\n")
            fh.write(f"file '{entries[-1][0]}'\n")

        vcodec = (["-c:v", "h264_videotoolbox", "-b:v", "8M"] if a.fast
                  else ["-c:v", "libx264", "-preset", "medium", "-crf", "19"])
        dst = f"{OUT}/clip{clip['id']}.mp4"
        print(f"→ clip{clip['id']}  {dur:.1f}s  ({len(seq)} kata, {len(lines)} baris)")
        subprocess.run(
            ["ffmpeg", "-v", "error", "-stats", "-y",
             "-ss", f"{clip['start']:.3f}", "-t", f"{dur:.3f}", "-i", f"{W}/source.mp4",
             "-loop", "1", "-i", f"{tmp}/header.png",
             "-f", "concat", "-safe", "0", "-i", f"{tmp}/list.txt",
             "-filter_complex", filtergraph(clip, st, src_w, src_h),
             "-map", "[v]", "-map", "0:a",
             "-af", "loudnorm=I=-14:TP=-1.5:LRA=11"] + vcodec +
            ["-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", "-b:a", "192k",
             "-movflags", "+faststart", "-t", f"{dur:.3f}", dst], check=True)
        shutil.rmtree(tmp, ignore_errors=True)

    print("dry-run selesai — review teks di atas, isi \"fixes\" di clips.json, lalu render."
          if a.dry_run else f"selesai → {OUT}")

main()
