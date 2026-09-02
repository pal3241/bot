# Discord Bot Manager

Bot Discord berbasis terminal dengan fitur berikut:

- Emoji Manager untuk upload, melihat, dan menghapus emoji.
- Terminal Chat dua arah antara terminal dan channel Discord.
- Voice TTS Queue untuk membacakan teks di voice channel.
- Fondasi Voice Converter modular untuk RVC/w-okada.
- Model Manager untuk mengimpor dan mengelola model RVC.
- Sena AI text chat dengan personality, history singkat, dan dukungan multilingual.

## Persyaratan

- Python 3.13 atau versi yang kompatibel.
- FFmpeg tersedia melalui `PATH`.
- Bot Discord dengan permission yang sesuai.
- Koneksi internet untuk Discord dan gTTS.

Periksa FFmpeg:

```powershell
ffmpeg -version
```

## Instalasi

Buka PowerShell di folder proyek:

```powershell
cd D:\bot
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Selalu jalankan bot menggunakan Python dari `.venv`. Python global mungkin tidak memiliki PyNaCl yang diperlukan untuk voice channel.

## Konfigurasi token

Buat atau perbarui file `.env`:

```env
TOKEN=TOKEN_BOT_DISCORD
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=API_KEY_OPENROUTER
OPENROUTER_MODEL=openai/gpt-4o-mini
```

Untuk memakai NVIDIA NIM, ganti konfigurasi provider:

```env
LLM_PROVIDER=nvidia_nim
NVIDIA_NIM_API_KEY=API_KEY_NVIDIA_NIM
NVIDIA_NIM_MODEL=meta/llama-3.1-8b-instruct
NVIDIA_NIM_BASE_URL=https://integrate.api.nvidia.com/v1
```

Hanya API key provider aktif yang wajib tersedia. Model dan provider dapat diganti melalui `.env` tanpa mengubah Assistant Core. Bot memvalidasi personality, provider, model, dan API key sebelum login ke Discord.

Panjang output AI dibatasi maksimal 30 token melalui `LLM_MAX_TOKENS` di `config.py`.

Jangan membagikan atau memasukkan `.env` ke Git.

Di Discord Developer Portal, buka pengaturan aplikasi lalu aktifkan:

```text
Bot > Privileged Gateway Intents > Message Content Intent
```

Permission bot yang diperlukan:

- View Channels
- Send Messages
- Connect
- Speak
- Create Expressions
- Manage Expressions

Permission expression diperlukan untuk Emoji Manager. Permission voice diperlukan untuk Voice TTS.

## Menjalankan bot

```powershell
cd D:\bot
.\.venv\Scripts\python.exe main.py
```

Setelah tersambung, menu berikut akan ditampilkan:

```text
1. Emoji Manager
2. Terminal Chat
3. Voice TTS
4. AI Settings
```

Ketik nomor menu untuk memilih fitur. Ketik `exit` untuk kembali atau menutup program.

Menu **AI Settings** berada pada nomor 4. Pengaturan provider, model, token, timeout, retry, session, history, bahasa, dan NVIDIA NIM URL dapat diubah saat bot berjalan. Nilainya disimpan otomatis ke `data/ai_settings.json`; API key tetap hanya dibaca dari `.env` dan tidak pernah disimpan di file pengaturan.

## Emoji Manager

Atur lokasi GIF dalam `config.py`:

```python
GIF_FOLDER: Path = Path(r"D:\Discord GIF")
```

Alur upload:

1. Pilih **Emoji Manager**.
2. Pilih server.
3. Pilih **Tambah semua GIF**.
4. Bot mengunggah seluruh `.gif` yang ukurannya tidak melebihi batas konfigurasi.

Nama emoji dibuat otomatis seperti `emoji0001`, `emoji0002`, dan seterusnya.

Menu **Hapus semua emoji** memerlukan konfirmasi `HAPUS`. Emoji managed milik integrasi lain tidak akan dihapus.

## Terminal Chat dua arah

1. Pilih **Terminal Chat**.
2. Pilih server.
3. Pilih text channel.
4. Pilih **Mulai chat**.
5. Ketik pesan di terminal untuk mengirimnya ke Discord.

Pesan baru dari channel yang dipilih akan tampil di terminal:

```text
NamaUser > pesan dari Discord
You >
```

Pesan lebih dari 2.000 karakter otomatis dipecah. Ketik `exit` untuk menghentikan sesi chat.

## Sena AI text chat

Sena tidak membalas seluruh channel secara otomatis. Setiap percakapan terpisah berdasarkan server, channel, dan user.

1. Mention bot, misalnya `@Sena hey`, untuk mengaktifkan sesi.
2. Lanjutkan chat biasa tanpa mention selama sesi masih aktif.
3. Gunakan `@Sena diam`, `@Sena tidur`, `@Sena stop`, `@Sena mute`, `@Sena shut up`, atau `@Sena sleep` untuk membisukan sesi.
4. Mention bot lagi untuk mengaktifkannya kembali.

Sesi ACTIVE kembali menjadi INACTIVE setelah 120 detik tanpa aktivitas. History hanya disimpan di RAM, dibatasi 20 message, dan dihapus saat sesi timeout, dibisukan, atau bot ditutup.

Personality aktif berada di:

```text
data/personality.txt
```

Edit file tersebut untuk mengubah gaya Sena. `PersonalityManager.reload()` tersedia untuk integrasi reload saat runtime; restart bot juga memuat versi file terbaru. Kebijakan bahasa default adalah `auto`, sehingga Sena mengikuti bahasa pesan terbaru secara natural.

## Voice TTS Queue

1. Pilih **Voice TTS**.
2. Pilih server.
3. Pilih voice channel.
4. Pilih **Join VC**.
5. Pilih **Terminal TTS Queue**.
6. Ketik teks yang ingin diucapkan bot.

Contoh:

```text
TTS > halo semuanya
QUEUE > ditambahkan, menunggu=1

VOICE [1] > mulai berbicara
VOICE [1] > selesai
```

Anda dapat terus menambahkan teks saat bot berbicara. Audio diproses satu per satu. Ketik `exit` untuk menunggu antrean selesai dan kembali.

TTS Queue menggunakan dua tahap terpisah:

```text
Text Queue -> Preparation TTS/RVC -> Ready Queue -> Discord Playback
```

Ketika audio pertama sedang diputar, audio berikutnya sudah dapat menjalankan TTS dan RVC. Ready queue dibatasi maksimal dua audio agar file sementara tidak menumpuk. Urutan pesan tetap dipertahankan dan hanya satu konversi RVC berjalan pada satu waktu.

Terminal menampilkan metrics performa seperti:

```text
[VOICE PERF] tts=0.320s rvc=2.410s total_prepare=2.730s
[VOICE PERF] queue_wait=0.050s playback_wait=0.000s playback=3.200s
```

Client w-okada menggunakan koneksi HTTP persisten dan melewati request konfigurasi yang nilainya tidak berubah. Cache otomatis direset ketika request backend gagal atau converter diganti.

Bahasa default adalah bahasa Indonesia dengan kode `id`. Gunakan menu **Pilih bahasa** untuk menggantinya, misalnya:

- `id` untuk bahasa Indonesia.
- `en` untuk bahasa Inggris.
- `ja` untuk bahasa Jepang.

## Voice Converter

Pipeline audio:

```text
Teks -> TTS Queue -> gTTS -> Voice Converter opsional -> FFmpeg -> Discord VC
```

Ketika converter OFF, audio gTTS langsung diputar di Discord. Ketika converter ON, audio diproses oleh converter yang dipilih sebelum diputar.

Converter yang tersedia:

- `passthrough`: menyalin audio tanpa mengubah suara. Gunakan untuk menguji pipeline converter.
- `rvc`: adapter RVC yang memerlukan backend RVC/w-okada yang kompatibel.

Untuk menguji fondasi converter:

1. Pilih **Pilih converter**.
2. Pilih `passthrough`.
3. Aktifkan **Voice Converter ON/OFF** hingga statusnya ON.
4. Pilih **Test suara** atau gunakan Terminal TTS Queue.

### Menjalankan backend RVC

Adapter `rvc` mendukung w-okada v2.0.78 pada URL berikut:

```text
http://127.0.0.1:18000
```

Jalankan backend pada terminal terpisah sebelum bot:

```powershell
cd D:\bot\dist
.\main.exe cui --https false --no_cui False
```

Tunggu sampai log menampilkan `Starting VCServer on port 18000`. Startup pertama akan mengunduh modul inference yang diperlukan.

Adapter memakai endpoint `/api/voice-changer/convert_chunk`, menormalisasi audio menjadi mono float32 48 kHz, lalu mengubah hasil menjadi WAV untuk Discord. Endpoint `convert_file` tidak digunakan karena rusak pada paket v2.0.78 ini.

Setelah backend aktif:

1. Pilih converter `rvc`.
2. Pilih **Pilih model** untuk melihat model lokal dan slot RVC backend.
3. Aktifkan Voice Converter.
4. Gunakan **Test suara** atau Terminal TTS Queue.

Jika model belum dipilih dari bot, adapter menggunakan slot yang sedang aktif pada UI w-okada.

Model dengan label `[LOCAL]` dibaca dari `models/rvc/<nama>`. Ketika dipilih, file `.pth` dan `.index` disalin sementara ke `dist/upload_dir` dan didaftarkan melalui API w-okada. File sumber di `models/rvc` tetap dipertahankan. Model yang sudah terdaftar ditampilkan sebagai slot backend dan tidak diunggah ulang.

## Model Manager RVC

Struktur penyimpanan model:

```text
models/
└── rvc/
    └── nama_model/
        ├── model.pth
        └── model.index
```

File `.index` bersifat opsional. Setiap folder model harus memiliki tepat satu file `.pth` dan maksimal satu file `.index`.

### Import model ZIP

1. Buka **Voice TTS > Model Manager**.
2. Pilih **Import model**.
3. Masukkan path lengkap file `.zip`.
4. Masukkan nama model.

Contoh path:

```text
C:\Users\nama\Downloads\miku.zip
```

ZIP hanya akan membaca file `.pth` dan `.index`. Path traversal di dalam ZIP ditolak dan isi model tidak pernah dieksekusi sebagai Python.

### Import file PTH

Masukkan path file `.pth` secara langsung. Jika folder sumber memiliki tepat satu file `.index`, file tersebut ikut disalin.

Model dapat dipilih melalui **Pilih model**. Penghapusan model memerlukan konfirmasi berikut:

```text
HAPUS nama_model
```

File model di dalam `models/rvc` diabaikan Git agar model berukuran besar tidak ikut terunggah.

## Pengaturan konversi

- Pitch: `-24` sampai `+24` semitone.
- Index ratio: `0.0` sampai `1.0`.
- Protect: `0.0` sampai `1.0`.

Pitch adalah bagian dari Voice Converter, bukan fitur gTTS. Pengaturan ini baru diterapkan oleh backend converter yang mendukungnya.

### Penyimpanan pengaturan

Pengaturan Voice TTS otomatis disimpan ke:

```text
data/voice_settings.json
```

Nilai berikut dipulihkan ketika menu Voice TTS dibuka kembali atau bot direstart:

- TTS engine.
- Bahasa.
- Status Voice Converter ON/OFF.
- Jenis converter.
- Slot model yang dipilih.
- Pitch.
- Index ratio.
- Protect.

File disimpan secara atomik dan divalidasi ketika dibaca. Jika JSON rusak atau memiliki tipe nilai yang salah, bot menampilkan lokasi dan detail field yang bermasalah. File ini merupakan preferensi lokal dan tidak dimasukkan ke Git.

## Pemecahan masalah

### PyNaCl library needed

Bot dijalankan memakai Python global. Gunakan:

```powershell
.\.venv\Scripts\python.exe main.py
```

### FFmpeg tidak ditemukan

Pasang FFmpeg dan pastikan perintah berikut bekerja:

```powershell
ffmpeg -version
```

### Bot tidak dapat masuk voice channel

Pastikan bot memiliki permission **View Channel**, **Connect**, dan **Speak** pada channel tersebut.

### Pesan Discord tidak muncul di terminal

Aktifkan **Message Content Intent** di Discord Developer Portal, lalu restart bot.

### Backend RVC tidak dapat dihubungi

Pastikan w-okada v2.0.78 berjalan pada `http://127.0.0.1:18000`. Matikan Voice Converter atau gunakan `passthrough` jika backend tidak sedang digunakan.
