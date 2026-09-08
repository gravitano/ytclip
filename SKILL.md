---
name: ytclip
description: "Turn a long YouTube video into short vertical clips (9:16, burned-in karaoke subtitles) the way OpusClip does — but the moment-picking is done by reading the transcript, not by a scoring heuristic. Use when the user says \"bikin clip dari YouTube\", \"clip video ini\", \"potong jadi shorts\", \"bikin reels dari podcast\", \"clipper\", \"kaya OpusClip\", \"jadiin konten pendek\", or pastes a YouTube URL and asks for short-form cuts. Handles podcasts/two-shot interviews (split layout), single speaker, and screenshare."
version: "1.0.0"
author: "GITS"
license: "MIT"
metadata:
  hermes:
    tags: [video, youtube, shorts, reels, tiktok, ffmpeg, content]
    category: content-production
---

Ubah satu video YouTube panjang jadi beberapa klip vertikal 1080x1920 siap unggah:
subtitle karaoke di-burn, judul hook di atas, audio dinormalisasi ke standar sosmed.

Nilai utama skill ini ada di **pemilihan momen** — itu dikerjakan dengan membaca
transkrip, bukan oleh heuristik skor. Script hanya mengurus mekanisnya.

Argumen (opsional):
- URL YouTube — kalau belum disebut, tanyakan
- `--n <angka>` — berapa klip (default 5–6)
- `--out <path>` — folder keluaran (default `./clips/<video-id>/`)
- `--lang <kode>` — bahasa caption (default: auto-detect)
- `--fast` — encode pakai VideoToolbox, lebih cepat, kualitas sedikit turun

## Prasyarat

`ffmpeg`, `ffprobe`, `uv`. `yt-dlp` dipasang otomatis oleh `fetch.py` bila belum ada.
`deno` sebaiknya ada (`brew install deno`) — tanpa JS runtime, yt-dlp kehilangan
sebagian format kualitas tinggi.

**Jangan pakai filter `subtitles` atau `drawtext`.** ffmpeg Homebrew umumnya dibuild
tanpa libass dan libfreetype, jadi kedua filter itu tidak ada. Cek cepat:
`ffmpeg -hide_banner -filters | grep -wE "drawtext|subtitles"`. Skill ini merender
subtitle sebagai PNG overlay lewat Pillow, jadi jalan di build ffmpeg apa pun.

## Alur

Kerjakan berurutan. Langkah 3 dan 6 butuh penilaianmu — jangan diserahkan ke script.

### 1. Siapkan workdir

Pakai scratchpad sesi untuk file antara (video sumber ratusan MB, jangan taruh di repo).
Folder keluaran taruh di tempat yang jelas bagi user.

### 2. Unduh video + transkrip

```bash
uv run ~/.claude/skills/ytclip/scripts/fetch.py "<url>" "$W"
```

Mengambil video ≤1080p dan auto-caption YouTube format `json3` — yang penting: json3
memuat **timing per kata**, jadi subtitle karaoke bisa presisi tanpa perlu Whisper.
Hasil: `source.mp4`, `words.json`, `transcript.txt`, `meta.json`.

Kalau video tidak punya auto-caption sama sekali, barulah transkripsikan sendiri
(`uv tool install mlx-whisper`, model `large-v3`) dan tulis `words.json` dengan
bentuk yang sama.

### 3. Baca transkrip, pilih momennya sendiri

**Baca `transcript.txt` seluruhnya** sebelum memilih. Ini bagian yang menentukan
kualitas hasil, dan tidak bisa didelegasikan ke script.

Yang membuat sebuah potongan layak jadi klip:
- **Ada hook di 3 detik pertama** — pernyataan kontrarian, angka mengejutkan,
  pertanyaan yang menantang asumsi. Klip yang dibuka dengan basa-basi akan mati.
- **Utuh sendiri** — bisa dipahami tanpa menonton bagian lain. Kalau butuh
  konteks dari 10 menit sebelumnya, lewati.
- **Punya penutup** — kesimpulan, punchline, atau cliffhanger. Jangan berhenti
  di tengah kalimat.
- **Satu gagasan saja.** Dua gagasan dalam satu klip berarti dua klip.

Sasaran durasi 25–45 detik. Di bawah 20 detik biasanya kurang isi; di atas 60 detik
retensinya turun.

Cari batas potong yang presisi dengan:
```bash
uv run ~/.claude/skills/ytclip/scripts/probe.py "$W" words 555 625
```
Mulai tepat di kata pertama hook (jangan sertakan "ee", "jadi", "nah" di depan),
akhiri sesudah kata terakhir penutup + ~0.3 detik.

### 4. Pilih layout dan ukur framing

```bash
uv run ~/.claude/skills/ytclip/scripts/probe.py "$W" frames 120 400 700 1000
uv run ~/.claude/skills/ytclip/scripts/probe.py "$W" grid 700     # frame + grid 10%
```

Baca gambarnya dengan tool Read, lalu **periksa dulu apakah sumbernya multicam**
— ini penentu pertama, bukan penentu terakhir:

```bash
ffmpeg -v error -ss 600 -t 300 -i "$W/source.mp4" \
  -vf "scale=320:-1,select='gt(scene,0.3)',metadata=print:file=-" -an -f null - \
  2>/dev/null | grep -c pts_time
```

Lebih dari ~1 potongan per menit berarti multicam. Jangan pernah memakai `split`
di situ: bingkai tetap akan menunjuk ruang kosong begitu kamera berganti, dan
separuh layar jadi dinding kosong.

Tangga keputusannya:

| Kondisi | Layout |
|---|---|
| Ada perpindahan shot di dalam klip | `track` |
| Kamera terkunci, 2 orang, terpisah lebar, selalu terlihat | `split` |
| Kamera terkunci, 1 orang | `single` |
| Slide, screenshare, atau isi frame yang tidak boleh dipotong | `fit` |

**Jangan menyaring `split` hanya lewat jumlah jangkar wajah.** Sumber multicam bisa
tetap menghasilkan tepat dua kelompok wajah yang meyakinkan — satu dari close-up,
satu dari wide shot — padahal keduanya berasal dari kamera yang berbeda. Deteksi
potongan adalah penjaganya; jumlah wajah per sampel yang stabil (mendekati 100%,
bukan sekadar "mayoritas") adalah penjaga keduanya.

Untuk `split` dan `single`, ukur titik tengah wajah dari frame ber-grid (tiap kotak
10%; pada 1920x1080 berarti 192x108 px).

Untuk `track`, pemetaannya otomatis:

```bash
uv run --with opencv-python-headless ~/.claude/skills/ytclip/scripts/shots.py \
  "$W/source.mp4" "$W/yunet.onnx" 596.1 648.5
```

Model YuNet diunduh sekali dari `opencv_zoo` (`face_detection_yunet_2023mar.onnx`).
Pada sumber besar, jalankan `shots.py` pada salinan resolusi rendah lalu skalakan
`cx`/`cy`/`fh` — posisi wajahnya sama dan jauh lebih cepat.

Terakhir, sampel frame di tengah tiap klip untuk memastikan layoutnya cocok dengan
segmen itu. Video sering berpindah antara talking head dan slide.

### 5. Tulis `clips.json`

Taruh di `$W/clips.json`. Lihat `reference/layouts.md` untuk skema lengkap.

```json
{
  "style": { "tag": "NAMA PODCAST  ·  CHANNEL" },
  "fixes": { "pipe": "vibe", "gpd": "GPT" },
  "drop":  ["penutan"],
  "clips": [
    { "id": "01", "start": 581.10, "end": 621.20, "layout": "split",
      "title": "\"SAYA PENGIN LIHAT\nKARYAWAN NGGAK ADA KERJAAN\"",
      "top":    { "cx": 200,  "cy": 440 },
      "bottom": { "cx": 1690, "cy": 400 } }
  ]
}
```

Judul: 2 baris, huruf kapital, ≤30 karakter per baris. Tulis sebagai hook, bukan
label topik — kutipan langsung yang paling tajam biasanya menang.

### 6. Dry-run, lalu koreksi salah dengar — wajib

```bash
uv run --with pillow ~/.claude/skills/ytclip/scripts/render.py "$W" --dry-run
```

Auto-caption YouTube **selalu** salah dengar nama produk, istilah teknis, dan nama
orang. Subtitle yang salah bikin klip terlihat murah. Baca keluaran dry-run, lalu
isi `fixes` (kunci = kata sumber huruf kecil tanpa tanda baca, nilai = penggantinya)
dan `drop` (kata yang dibuang dari subtitle — audionya tetap utuh). Ulangi
sampai teksnya bersih.

Yang biasanya perlu dikoreksi: nama produk/framework, akronim, nama orang, angka
yang salah tulis, dan kata garbled yang tidak bisa dipulihkan (buang lewat `drop`).

**Jangan menebak istilah yang tidak kamu yakini.** Kalau ada kata yang jelas salah
dengar tapi maksudnya tidak pasti, pilih potongan yang tidak memuatnya, atau
laporkan ke user dan minta konfirmasi. Menebak nama produk lebih buruk daripada
membiarkannya.

### 7. Render dan verifikasi

```bash
uv run --with pillow ~/.claude/skills/ytclip/scripts/render.py "$W" "<outdir>"
uv run ~/.claude/skills/ytclip/scripts/probe.py "$W" check "<outdir>/clip01.mp4" 5 15 25
```

Baca contact sheet-nya. Yang dicek: wajah tidak terpotong di kedua panel, subtitle
tidak menutupi mulut, judul tidak terpotong, kata aktif tersorot pas.

Verifikasi spesifikasi: `ffprobe` harus melaporkan 1080x1920 dan durasi sesuai
`clips.json`.

### 8. Laporkan

Tabel: nama file, timecode sumber, durasi, hook. Sebutkan koreksi ASR yang dilakukan
dan istilah apa pun yang tidak kamu yakini.

## Catatan

- **Hak cipta.** Skill ini untuk mengklip video milik user sendiri atau yang ia punya
  hak untuk pakai. Kalau videonya jelas milik pihak lain dan tujuannya redistribusi,
  konfirmasi dulu ke user.
- Render ~4x realtime dengan libx264 pada Apple Silicon. `--fast` memakai
  VideoToolbox bila butuh lebih cepat.
- Audio dinormalisasi ke −14 LUFS (standar Shorts/Reels/TikTok). Jangan diubah
  kecuali user minta.
- Simpan `clips.json` di folder keluaran bersama hasil render — itu satu-satunya
  yang dibutuhkan untuk merender ulang.
