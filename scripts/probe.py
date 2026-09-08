#!/usr/bin/env python3
"""Alat inspeksi: lihat timing kata & framing video sebelum menulis clips.json.

  uv run probe.py <workdir> words <start> <end>     timing per kata di rentang detik
  uv run probe.py <workdir> grid <t>                frame + grid 10% untuk mengukur crop
  uv run probe.py <workdir> frames <t1> <t2> ...    contact sheet beberapa detik
  uv run probe.py <workdir> check <mp4> <t1> ...    contact sheet dari klip hasil render

`grid` dan `frames` menulis PNG/JPG di <workdir>/probe/ — baca dengan tool Read.
"""
import json, os, subprocess, sys

def ff(args):
    subprocess.run(["ffmpeg", "-v", "error", "-y"] + args, check=True)

def sheet(paths, out, cols, width=380):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-pattern_type", "glob",
                    "-i", paths, "-filter_complex",
                    f"scale={width}:-1,tile={cols}x{(len(os.listdir(os.path.dirname(paths)))+cols-1)//cols}",
                    out], check=True)

def main():
    W = os.path.abspath(sys.argv[1]); cmd = sys.argv[2]
    P = f"{W}/probe"; os.makedirs(P, exist_ok=True)

    if cmd == "words":
        a, b = float(sys.argv[3]), float(sys.argv[4])
        ws = json.load(open(f"{W}/words.json"))
        print(" | ".join(f"{w['t']:.2f} {w['w']}" for w in ws if a <= w["t"] <= b))

    elif cmd == "grid":
        t = sys.argv[3]
        out = f"{P}/grid_{t}.jpg"
        ff(["-ss", t, "-i", f"{W}/source.mp4", "-frames:v", "1",
            "-vf", "drawgrid=w=iw/10:h=ih/10:t=2:c=red@0.8", "-q:v", "3", out])
        print(out)
        print("tiap kotak = 10% lebar/tinggi. Hitung titik tengah wajah dalam piksel sumber.")

    elif cmd in ("frames", "check"):
        src = f"{W}/source.mp4" if cmd == "frames" else sys.argv[3]
        times = sys.argv[3:] if cmd == "frames" else sys.argv[4:]
        d = f"{P}/{cmd}"; subprocess.run(["rm", "-rf", d]); os.makedirs(d)
        for i, t in enumerate(times, 1):
            ff(["-ss", t, "-i", src, "-frames:v", "1", "-q:v", "4", f"{d}/f{i:02d}.jpg"])
        cols = min(4, len(times))
        rows = (len(times) + cols - 1) // cols
        out = f"{P}/{cmd}_sheet.jpg"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-pattern_type", "glob",
                        "-i", f"{d}/f*.jpg", "-filter_complex",
                        f"scale=380:-1,tile={cols}x{rows}", out], check=True)
        print(out)
    else:
        sys.exit(__doc__)

main()
