# Bagaimana klip itu dibuat

Catatan proses dari sesi pertama yang melahirkan skill ini: satu episode podcast
berdurasi 30 menit diubah menjadi enam klip vertikal siap unggah. Ditulis sebagai
studi kasus supaya keputusan-keputusannya bisa ditelusuri, bukan sekadar
perintahnya bisa diulang. Untuk instruksi kerja, baca `SKILL.md`; untuk skema dan
rumus, baca `reference/layouts.md`.

Sumbernya: *Founder Inside* — GITS Indonesia, 1782 detik, dua orang, kamera statis.

## 1. Memeriksa perkakas

`ffmpeg` dan `ffprobe` sudah terpasang. `yt-dlp` dan Whisper belum. `yt-dlp` dipasang
lewat `uv tool install`, dan `deno` lewat Homebrew — tanpa JS runtime, yt-dlp
memperingatkan bahwa sebagian format kualitas tinggi tidak bisa diambil.

Mesinnya Apple M5, dan `ffmpeg` punya encoder VideoToolbox. Itu dicatat sebagai
opsi cepat, tapi render akhir tetap memakai libx264 demi kualitas.

## 2. Mengunduh video dan transkrip

Di sinilah satu langkah berat terpotong. Auto-caption YouTube bisa diminta dalam
format `json3`, dan format itu **memuat timing per kata**, bukan hanya per baris:

```json
{ "tStartMs": 581100, "segs": [ { "utf8": "pokoknya", "tOffsetMs": 140 } ] }
```

Artinya subtitle karaoke bisa presisi tanpa menjalankan Whisper sama sekali.
Hasilnya 5.267 kata bertimestamp untuk video 30 menit, terunduh dalam hitungan detik.

Transkrip diubah jadi dua bentuk. `words.json` untuk mesin, dan `transcript.txt`
berisi blok 20 detik ber-timestamp untuk dibaca manusia — 88 blok, sekitar 33 KB.

Kalau video tidak punya auto-caption sama sekali, barulah `mlx-whisper` dipakai
dan hasilnya ditulis ke bentuk `words.json` yang sama.

## 3. Memilih momen

Bagian ini dikerjakan dengan membaca seluruh transkrip, bukan oleh script. Inilah
yang menentukan apakah klipnya layak tonton, dan tidak ada heuristik skor yang
bisa menggantikannya.

Kriteria yang dipakai:

- **Hook di 3 detik pertama.** Pernyataan kontrarian, angka mengejutkan, atau
  pertanyaan yang menantang asumsi. Klip yang dibuka dengan basa-basi akan mati.
- **Utuh sendiri.** Bisa dipahami tanpa menonton bagian lain.
- **Punya penutup.** Kesimpulan, punchline, atau cliffhanger.
- **Satu gagasan saja.** Dua gagasan berarti dua klip.
- **Durasi 25–45 detik.** Di bawah 20 detik kurang isi, di atas 60 detik retensinya turun.

Enam yang terpilih:

| Klip | Sumber | Durasi | Hook |
|---|---|---|---|
| 01 | 09:41–10:21 | 40s | CEO ingin karyawannya tidak punya kerjaan — dan alasannya |
| 02 | 16:38–17:15 | 37s | Satu orang melayani 2.600 masjid, ditutup tantangan skala 100.000 |
| 03 | 07:47–08:20 | 33s | Developer memakai AI diam-diam, informasinya ditahan dari atasan |
| 04 | 07:04–07:33 | 29s | Perusahaan IT masih gagap AI |
| 05 | 19:39–20:17 | 38s | Ketakutan source code diambil AI dianggap sudah tidak relevan |
| 06 | 27:37–28:04 | 27s | Dashboard dinilai akan tertinggal karena statis |

Batas potong dipresisikan dari timing per kata:

```bash
uv run scripts/probe.py "$W" words 555 625
```

Klip dimulai tepat di kata pertama hook — bukan di "ee", "nah", atau "jadi" yang
mendahuluinya — dan berhenti sesudah kata terakhir penutup.

## 4. Menentukan framing

Beberapa frame disampel lebih dulu. Ternyata kamera statis dengan two-shot: host di
kiri, narasumber di kanan, keduanya selalu dalam frame.

Itu langsung menyingkirkan center crop. Crop 9:16 di tengah akan memotong kedua
orang sekaligus, sementara memilih salah satu sisi berarti membuang lawan bicaranya.
Yang dipakai adalah **split stacked** — tiap orang di-crop terpisah lalu ditumpuk
atas-bawah. Karena keduanya selalu terlihat, diarisasi pembicara tidak diperlukan.

Posisi wajah diukur dari satu frame ber-grid 10%:

```bash
uv run scripts/probe.py "$W" grid 700
```

Pada frame 1920x1080, tiap kotak berukuran 192x108 px. Host jatuh di sekitar
`cx=200, cy=440`, narasumber di `cx=1690, cy=400`.

Crop dihitung memusat ke titik itu lalu dijepit ke tepi frame — dan penjepitannya
bukan sekadar pengaman. Host menghasilkan koordinat x negatif yang dijepit ke nol,
sehingga ia menempel ke kiri panel dan ruang kosongnya jatuh di kanan, searah
pandangannya ke lawan bicara. Simetris untuk narasumber. Lookroom muncul sendiri
tanpa bias manual.

Langkah terakhir: frame di tengah tiap klip disampel untuk memastikan tidak ada yang
jatuh di segmen slide. Video ini berpindah-pindah antara talking head dan screenshare,
dan layout `split` akan salah total kalau dipakai di segmen slide.

## 5. `clips.json` yang dipakai

```json
{
  "style": { "tag": "FOUNDER INSIDE  ·  GITS INDONESIA" },
  "fixes": { "pipe": "vibe", "pip": "vibe", "gpd": "GPT", "sc": "source" },
  "drop": ["penutan"],
  "clips": [
    { "id": "01", "start": 581.10, "end": 621.20, "layout": "split",
      "title": "\"SAYA PENGIN LIHAT\nKARYAWAN NGGAK ADA KERJAAN\"",
      "top":    { "cx": 200,  "cy": 440 },
      "bottom": { "cx": 1690, "cy": 400 } }
  ]
}
```

Judul ditulis sebagai hook, bukan label topik. Kutipan langsung yang paling tajam
biasanya menang atas rangkuman.

## 6. Dua masalah yang muncul

### ffmpeg tanpa libass dan libfreetype

Filter `subtitles`, `ass`, dan `drawtext` sama sekali tidak ada di build Homebrew
yang terpasang — dan itu baru ketahuan saat filtergraph dijalankan.

```bash
ffmpeg -hide_banner -filters | grep -wE "drawtext|subtitles"   # kosong
```

Jalan keluarnya bukan mengganti ffmpeg, melainkan tidak memakai kedua filter itu:
subtitle dirender sebagai PNG per kata aktif lewat Pillow, dirangkai dengan concat
demuxer, lalu di-overlay sekali. Pendekatan ini jalan di build ffmpeg mana pun, dan
stylingnya justru lebih bebas daripada ASS.

### Baris subtitle diawali ekor kalimat sebelumnya

Render pertama menghasilkan baris seperti `"GITU. ITU HARUS BISA"` — kata penutup
kalimat sebelumnya terbawa ke awal baris berikutnya, dan itu terbaca seperti salah
ketik.

Penyebabnya: pengelompokan hanya memotong berdasarkan lebar baris dan jumlah kata.
Perbaikannya, kata dipecah **per kalimat dulu**, baru tiap kalimat dipotong per
lebar. Dengan begitu tidak ada baris yang menyeberangi batas kalimat.

## 7. Mengoreksi salah dengar

Auto-caption YouTube selalu salah pada nama produk, istilah teknis, dan nama orang.
Subtitle yang salah membuat klip terlihat murah, jadi teksnya dicetak dulu untuk
direview sebelum ada yang dirender:

```bash
uv run --with pillow scripts/render.py "$W" --dry-run
```

Yang dikoreksi di sesi ini antara lain *vibe coding*, SITCOM, MASLAM, GITS,
*source code*, Ghibli, dan "di-sue" — semuanya lewat `fixes`. Kata garbled yang
tidak bisa dipulihkan dibuang lewat `drop`; audionya tetap utuh, hanya subtitlenya
yang bersih.

Satu istilah sengaja tidak ditebak karena maksudnya tidak pasti. Menebak nama
produk lebih buruk daripada membiarkannya, jadi potongan yang memuatnya dihindari
dan ketidakpastiannya dilaporkan ke user.

## 8. Render dan verifikasi

Tiap klip disusun dari dua panel, band judul di atas, dan subtitle karaoke.
Audio dinormalisasi ke −14 LUFS mengikuti standar Shorts, Reels, dan TikTok.
Encode memakai libx264 CRF 19.

Total 205 detik video selesai dalam 67 detik — sekitar 3x realtime.

Verifikasi tidak berhenti di "tidak ada error". Frame diambil dari file hasil lalu
benar-benar dilihat:

```bash
uv run scripts/probe.py "$W" check out/clip01.mp4 5 15 25
```

Yang diperiksa: wajah tidak terpotong di kedua panel, subtitle tidak menutupi mulut,
judul tidak terpotong di tepi, dan kata aktif tersorot pas. Ditambah `ffprobe` untuk
memastikan 1080x1920 dan durasinya sesuai `clips.json`.

## Pembagian kerja

Script mengurus yang mekanis: unduh, parse, hitung crop, render, normalisasi audio.

Tiga hal dikerjakan dengan penilaian, dan sengaja tidak diotomatiskan:

1. **Momen mana yang layak jadi klip** — butuh membaca transkrip utuh.
2. **Di mana tepatnya memotong** — batas kalimat, bukan batas waktu.
3. **Teks subtitle mana yang salah dengar** — butuh tahu domainnya.

Ketiganya adalah tempat kualitas hasil ditentukan. Menggantinya dengan skor
otomatis akan menghasilkan klip yang secara teknis benar tapi tidak ada yang
menontonnya sampai habis.
