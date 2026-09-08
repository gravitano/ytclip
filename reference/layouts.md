# Skema `clips.json`, layout, dan matematika crop

## Skema lengkap

```json
{
  "style": {
    "head_h": 170,
    "cap_y": 1400,
    "cap_h": 380,
    "size": 68,
    "max_w": 960,
    "max_words": 4,
    "title_size": 54,
    "tag_size": 30,
    "hilite": [255, 214, 10],
    "bg": "0x0B0B0F",
    "tag": "NAMA PODCAST  ·  CHANNEL"
  },
  "fixes": { "<kata-sumber-huruf-kecil>": "<pengganti>" },
  "drop":  ["<kata-yang-dibuang-dari-subtitle>"],
  "clips": [ { ... } ]
}
```

`style`, `fixes`, `drop` semuanya opsional. Kalau file-nya berupa array biasa,
isinya dianggap `clips` saja dengan style default.

### Kunci per klip

| Kunci | Wajib | Arti |
|---|---|---|
| `id` | ya | Dipakai jadi nama file `clip<id>.mp4` |
| `start`, `end` | ya | Detik pada video sumber, boleh pecahan |
| `title` | ya | Judul di band atas, `\n` untuk baris kedua |
| `layout` | — | `split` (default), `track`, `single`, atau `fit` |
| `top`, `bottom` | untuk `split` | Titik wajah tiap panel |
| `face` | untuk `single` | Titik wajah |
| `shots` | untuk `track` | Daftar shot dari `shots.py` |
| `face_ratio` | untuk `track` | Porsi tinggi layar yang diisi wajah (bawaan 0.45) |

### Objek wajah

| Kunci | Default | Arti |
|---|---|---|
| `cx`, `cy` | — | Titik tengah wajah dalam piksel sumber |
| `zoom` | 1.35 | Makin besar makin dekat. 1.0 = tinggi frame penuh |
| `headroom` | 0.43 | Posisi vertikal wajah dalam panel. Kecil = wajah naik |

## Layout

### `split` — dua orang, kamera statis

**Syaratnya kamera terkunci satu angle.** Pada sumber multicam layout ini gagal
total: jangkar dihitung sekali untuk seluruh klip, jadi begitu kamera berganti ke
close-up, panel yang satunya menunjuk ruang kosong. Periksa potongan lebih dulu —
jumlah jangkar saja tidak cukup, karena multicam pun bisa menghasilkan tepat dua.

Dua panel ditumpuk, masing-masing 1080 x `(1920 - head_h) / 2`. Ini pilihan yang
benar untuk podcast two-shot: center crop biasa akan memotong kedua orang sekaligus,
sementara memilih salah satu berarti membuang lawan bicaranya.

Kedua orang selalu terlihat, jadi tidak perlu diarisasi pembicara. Panel atas
sebaiknya diisi host (yang lebih sering menyela), panel bawah narasumber — subtitle
jatuh di panel bawah, dekat orang yang paling banyak bicara.

### `track` — sumber multicam

Satu bingkai tegak yang berpindah mengikuti wajah, **berganti tepat di potongan
yang sudah ada di sumber**. Ini layout untuk video yang kameranya berpindah —
wawancara multicam, apa pun dengan lebih dari ~1 potongan per menit.

Kunci kenyamanannya ada pada penjadwalan: perpindahan bingkai dijatuhkan persis di
titik sumber sudah memotong. Di situ gambarnya memang berganti total, jadi lompatan
bingkai tidak terbaca sebagai kesalahan. Memindahkan bingkai di tengah shot —
entah digeser halus atau dipotong — selalu terbaca sebagai glitch, karena kameranya
sendiri tidak bergerak.

**Tiap shot mendapat ukuran crop sendiri**, dihitung dari tinggi wajah yang
terdeteksi, supaya wajah menempati porsi layar yang sama di semua shot:

```
ch = fh / face_ratio        fh = tinggi wajah di shot itu, face_ratio ~0.45
cw = ch * 1080 / 1920
```

Tanpa normalisasi ini, potongan ke wide shot terbaca sebagai zoom-out mendadak.
Diukur pada satu podcast ultrawide 3840x1600: wajah mengisi 43-49% tinggi layar di
close-up tetapi hanya 25-27% di wide shot — hampir dua kali lipat selisihnya.

Karena ukuran crop berbeda per shot, filter `crop` tidak bisa dipakai sendirian:
lebar dan tinggi crop hanya dievaluasi sekali saat filter dikonfigurasi, cuma `x`
dan `y` yang bisa berubah per frame. Jadi tiap shot di-`trim` jadi cabang sendiri,
di-crop dengan geometrinya sendiri, lalu disambung dengan filter `concat` — tetap
satu pass encoding.

### `single` — satu pembicara

Satu crop mengisi seluruh 1080x1920. Naikkan `zoom` (1.6–2.2) untuk close-up.

### `fit` — screenshare, slide, demo

Video utuh diskalakan selebar 1080 dan diletakkan di tengah, latar belakang diisi
versi ter-blur dari frame yang sama. Tidak ada yang terpotong. Pakai ini kalau isi
frame itu sendiri yang penting.

## Matematika crop

Untuk panel `pw x ph` pada sumber `src_w x src_h`:

```
ch = src_h / zoom                     tinggi crop
cw = ch * pw / ph                     lebar crop, mengikuti aspek panel
x  = clamp(cx - cw/2,  0, src_w - cw)
y  = clamp(cy - ch*headroom, 0, src_h - ch)
```

Penjepitan itu bukan sekadar pengaman — di situlah lookroom muncul. Orang yang duduk
di kiri frame menghasilkan `x` negatif, dijepit jadi 0, sehingga ia menempel ke kiri
panel dan ruang kosong jatuh di kanan, searah pandangannya ke lawan bicara. Simetris
untuk orang di kanan. Tidak perlu bias manual.

Contoh, sumber 1920x1080, layout `split` (panel 1080x875), `zoom` 1.35:
`ch = 800`, `cw = 987`. Wajah kiri di `cx=200` → `x = -293` → dijepit ke `0`.
Wajah kanan di `cx=1690` → `x = 1197` → dijepit ke `933`.

## Subtitle

Dirender sebagai PNG per kata aktif, lalu dirangkai lewat concat demuxer ffmpeg dan
di-overlay sekali. Alasannya: ffmpeg Homebrew umumnya tanpa libass/libfreetype,
sehingga filter `subtitles` dan `drawtext` tidak tersedia.

Pengelompokan baris memotong **per kalimat dulu**, baru per lebar. Tanpa itu, sebuah
baris bisa diawali ekor kalimat sebelumnya — `"GITU. ITU HARUS BISA"` — yang terbaca
seperti kesalahan.

Satu kata aktif disorot dengan warna `hilite`; sisanya putih. Semua teks memakai
stroke hitam tebal plus bayangan supaya terbaca di atas latar terang mana pun.

## Masalah yang sering muncul

| Gejala | Sebab | Perbaikan |
|---|---|---|
| `Unknown filter 'subtitles'` / `'drawtext'` | ffmpeg tanpa libass/libfreetype | Sudah tidak dipakai. Jangan tambahkan. |
| yt-dlp memperingatkan soal JS runtime | `deno` belum ada | `brew install deno` |
| Caption habis sebelum klip selesai | Ada jeda bicara panjang di akhir | Normal — `eof_action=pass` menahan frame terakhir |
| Wajah terpotong di panel | `cx`/`cy` salah ukur | Ukur ulang lewat `probe.py grid` |
| Subtitle menutupi mulut | Wajah terlalu rendah di panel | Kecilkan `headroom`, atau naikkan `cap_y` |
| Judul terpotong di tepi | Baris terlalu panjang | ≤30 karakter per baris, atau kecilkan `title_size` |
| Klip kena segmen slide | Video berpindah shot | Sampel frame di tengah klip, ganti ke layout `fit` |
| Bingkai meleset ke dinding kosong | `split` dipakai pada sumber multicam | Deteksi potongan dulu; pakai `track` |
| Klip seperti zoom-out saat potongan | `fh` tidak terisi di `shots` | Jalankan ulang `shots.py`, pastikan `fh` ada |
| Wajah salah dibingkai di wide shot | `shots.py` memilih wajah terbesar | Setel `cx`/`cy` shot itu manual di `clips.json` |

## Kalau tidak ada auto-caption

```bash
uv tool install mlx-whisper                      # Apple Silicon
mlx_whisper source.mp4 --model large-v3 --word-timestamps True --output-format json
```

Ubah hasilnya jadi `words.json` dengan bentuk `[{"t": detik, "w": kata}, ...]`.
Sisa pipeline tidak berubah.
