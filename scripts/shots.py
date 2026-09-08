#!/usr/bin/env python3
"""Petakan perpindahan shot dalam satu rentang, lalu cari posisi wajah per shot.

  uv run --with opencv-python-headless shots.py <video> <model.onnx> <start> <end>

Keluar JSON: {"source":[w,h], "shots":[{"t0","t1","cx","cy","fh","faces"}, ...]}
Waktu relatif terhadap <start>; cx/cy/fh dalam piksel sumber.

`fh` (tinggi wajah) dipakai render.py untuk menyamakan ukuran wajah antar
shot. Tanpa itu, potongan ke wide shot terbaca sebagai zoom-out mendadak.

Boleh dijalankan pada salinan resolusi rendah dari video yang sama —
posisi wajah sama saja, dan jauh lebih cepat. Skalakan cx/cy/fh dengan
rasio resolusinya sebelum dipakai merender.
"""
import json, subprocess, sys, statistics
import cv2, numpy as np

video, model, start, end = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4])
dur = end - start
MIN_SHOT = 0.8          # shot lebih pendek dari ini digabung ke tetangganya
SAMPLES_PER_SHOT = 6

def cuts_in_range():
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", str(start), "-t", str(dur), "-i", video,
         "-vf", "scale=320:-1,select='gt(scene,0.3)',metadata=print:file=-",
         "-an", "-f", "null", "-"], capture_output=True, text=True)
    out = []
    for line in p.stdout.splitlines():
        if "pts_time:" in line:
            out.append(float(line.split("pts_time:")[1].split()[0]))
    return out

# segmen shot
bounds = [0.0] + [c for c in cuts_in_range() if MIN_SHOT < c < dur - MIN_SHOT] + [dur]
segs = [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]
segs = [s for s in segs if s[1] - s[0] >= MIN_SHOT] or [(0.0, dur)]

cap = cv2.VideoCapture(video)
W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
det = cv2.FaceDetectorYN.create(model, "", (W, H), 0.6, 0.3, 5000)
det.setInputSize((W, H))

def _dominant(samples, frame_w):
    """Pilih SATU orang dari kumpulan wajah lintas sampel.

    Mediannya tidak boleh diambil langsung dari semua wajah: pada wide shot
    dua orang, sebagian sampel memilih yang kiri dan sebagian yang kanan,
    dan median dari sebaran bimodal itu mendarat di celah KOSONG di antara
    keduanya — bingkai berisi dinding, bukan orang.

    Maka wajah dikelompokkan dulu berdasarkan posisi x, lalu diambil
    kelompok yang paling sering muncul; bila seri, yang wajahnya paling
    besar (paling dekat kamera).
    """
    if not samples:
        return None
    gap = frame_w * 0.08
    groups = []
    for cx, cy, fh in sorted(samples):
        if groups and cx - groups[-1][-1][0] <= gap:
            groups[-1].append((cx, cy, fh))
        else:
            groups.append([(cx, cy, fh)])
    best = max(groups, key=lambda g: (len(g), statistics.mean(f[2] for f in g)))
    return (statistics.median([f[0] for f in best]),
            statistics.median([f[1] for f in best]),
            statistics.median([f[2] for f in best]),
            len(groups))

result = []
for t0, t1 in segs:
    seen, counts = [], []
    for k in range(SAMPLES_PER_SHOT):
        # hindari tepi shot — frame transisi sering kotor
        t = t0 + (t1 - t0) * (k + 0.5) / SAMPLES_PER_SHOT
        cap.set(cv2.CAP_PROP_POS_MSEC, (start + t) * 1000)
        ok, frame = cap.read()
        if not ok:
            continue
        _, faces = det.detect(frame)
        if faces is None:
            counts.append(0); continue
        counts.append(len(faces))
        for f in faces:
            seen.append((float(f[0] + f[2] / 2), float(f[1] + f[3] / 2), float(f[3])))
    pick = _dominant(seen, W)
    n = len(counts) or 1
    result.append({
        "t0": round(t0, 2), "t1": round(t1, 2),
        "cx": round(pick[0]) if pick else W // 2,
        "cy": round(pick[1]) if pick else H // 2,
        "fh": round(pick[2]) if pick else 0,
        "orang": pick[3] if pick else 0,
        "faces": round(statistics.mean(counts), 1) if counts else 0,
    })
cap.release()
print(json.dumps({"source": [W, H], "shots": result}, indent=1))
