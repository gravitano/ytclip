# ytclip

Claude Skill: mengubah video YouTube panjang menjadi klip vertikal 1080x1920
bersubtitle karaoke — seperti OpusClip, tapi pemilihan momennya dilakukan dengan
membaca transkrip, bukan oleh heuristik skor.

Satu link masuk, beberapa klip 9:16 keluar: subtitle di-burn, judul hook di atas,
audio dinormalisasi ke −14 LUFS.

## Pemasangan

```bash
git clone git@github.com:gravitano/ytclip.git ~/.claude/skills/ytclip
```

Skill terbaca pada sesi Claude Code berikutnya. Panggil dengan `/ytclip`, atau
cukup tempel URL YouTube dan minta klip pendek.

## Prasyarat

| Perkakas | Catatan |
|---|---|
| ffmpeg + ffprobe | build apa pun; libass tidak diperlukan |
| uv | menyediakan Python dan Pillow saat dijalankan |
| yt-dlp | dipasang otomatis oleh `fetch.py` bila belum ada |
| deno | opsional tapi disarankan — tanpa JS runtime, yt-dlp kehilangan sebagian format kualitas tinggi |

## Isi

| Berkas | Fungsi |
|---|---|
| `SKILL.md` | Alur kerja dan kriteria pemilihan momen |
| `scripts/fetch.py` | Unduh video + transkrip word-level dari auto-caption `json3` |
| `scripts/probe.py` | Inspeksi timing kata dan framing video |
| `scripts/shots.py` | Petakan potongan shot + posisi/ukuran wajah per shot |
| `scripts/render.py` | Render klip; layout `split`, `track`, `single`, `fit` |
| `reference/layouts.md` | Skema `clips.json`, matematika crop, troubleshooting |
| `docs/cara-kerja.md` | Studi kasus: bagaimana enam klip pertama dibuat, dan kenapa keputusannya begitu |

## Penggunaan langsung

```bash
W=$(mktemp -d)
uv run scripts/fetch.py "https://www.youtube.com/watch?v=..." "$W"
# baca $W/transcript.txt, pilih momennya, tulis $W/clips.json
uv run scripts/probe.py "$W" grid 700            # ukur titik wajah untuk crop
uv run --with pillow scripts/render.py "$W" --dry-run   # review teks subtitle
uv run --with pillow scripts/render.py "$W" ./out
```

## Catatan desain

**Auto-caption `json3` memuat timing per kata.** Karena itu subtitle karaoke bisa
presisi tanpa menjalankan Whisper sama sekali.

**Subtitle dirender sebagai PNG overlay, bukan ASS.** ffmpeg Homebrew umumnya
dibuild tanpa libass dan libfreetype, sehingga filter `subtitles` dan `drawtext`
tidak tersedia. Pendekatan PNG jalan di build ffmpeg mana pun.

**Crop dijepit ke tepi frame, dan itu disengaja.** Orang yang duduk di kiri frame
menghasilkan koordinat crop negatif yang dijepit ke nol, sehingga ia menempel ke
kiri panel dan ruang kosongnya jatuh searah pandangannya ke lawan bicara. Lookroom
muncul sendiri tanpa bias manual.

**Perpindahan bingkai dijatuhkan di potongan sumber.** Layout `track` mengganti
bingkai persis saat sumber sudah memotong, jadi lompatannya tak terlihat — dan tiap
shot dapat ukuran crop sendiri supaya wajah tetap seukuran di semua shot.

**Pemilihan momen sengaja tidak diotomatiskan.** Di situlah kualitas hasil
ditentukan, dan itu butuh membaca transkrip — bukan menghitung skor.

## Lisensi

MIT
