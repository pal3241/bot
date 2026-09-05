# Discord Bot Manager

Bot Discord berbasis terminal dengan fitur berikut:

- Emoji Manager untuk upload, melihat, dan menghapus emoji.
- Terminal Chat dua arah antara terminal dan channel Discord.
- Voice System untuk Terminal TTS, Voice Changer, dan STT percakapan.
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
SENA_OWNER_ID=123456789012345678
```

Untuk memakai NVIDIA NIM, ganti konfigurasi provider:

```env
LLM_PROVIDER=nvidia_nim
NVIDIA_NIM_API_KEY=API_KEY_NVIDIA_NIM
NVIDIA_NIM_MODEL=meta/llama-3.1-8b-instruct
NVIDIA_NIM_BASE_URL=https://integrate.api.nvidia.com/v1
```

Hanya API key provider aktif yang wajib tersedia. Model dan provider dapat diganti melalui `.env` tanpa mengubah Assistant Core. Bot memvalidasi personality, provider, model, dan API key sebelum login ke Discord.

Panjang output AI dibatasi maksimal 300 token melalui `LLM_MAX_TOKENS` di `config.py`.
Untuk NVIDIA Nemotron, thinking dinonaktifkan pada request agar batas tersebut dipakai untuk jawaban final dan bukan reasoning internal.

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
3. Voice
4. AI Settings
```

Ketik nomor menu untuk memilih fitur. Ketik `exit` untuk kembali atau menutup program.

Menu **AI Settings** berada pada nomor 4. Pengaturan provider, model, token, timeout, retry, session, history, bahasa, dan NVIDIA NIM URL dapat diubah saat bot berjalan. Nilainya disimpan otomatis ke `data/ai_settings.json`; API key tetap hanya dibaca dari `.env` dan tidak pernah disimpan di file pengaturan.

### Keamanan Control Center

Web UI bind ke `0.0.0.0` secara default agar dashboard dapat dibuka dari laptop
atau device lain di LAN. PIN bersifat opsional, tetapi sebaiknya diisi:

```env
SENA_WEB_HOST=0.0.0.0
SENA_WEB_PORT=8550
SENA_WEB_PIN=ubah-dengan-pin-yang-kuat
```

Jika `SENA_WEB_PIN` kosong, dashboard tetap bisa dibuka dari LAN dan Senna
menampilkan peringatan keamanan di log. Gunakan `SENA_WEB_HOST=127.0.0.1` jika
ingin membatasi dashboard ke device host. Tombol logout, reset chat session,
restart, dan shutdown tersedia di tab **Settings**. Reset session hanya
membersihkan history jangka pendek serta status aktif/diam; memory jangka
panjang, personality, jadwal, dan konfigurasi tidak ikut dihapus.

## Prompt prefill dan model routing

Sena membagi request AI menjadi tiga tier secara deterministik:

- `FAST`: sapaan, reaksi, dan pesan singkat sederhana.
- `STANDARD`: pertanyaan normal seperti `kenapa python populer?` atau history yang mulai panjang.
- `COMPLEX`: traceback nyata, code block, refactor/arsitektur yang berat, memory eksplisit, dan action planning.

Jalur `COMPLEX` default menggunakan NVIDIA NIM model
`moonshotai/kimi-k3`. FAST dan STANDARD default memakai OpenRouter; konfigurasi
lama yang mengarahkannya ke NVIDIA dikoreksi ke OpenRouter saat runtime.
Jika target route gagal, router mencoba model fallback lalu model utama.

Structured response menggunakan JSON mode. OpenRouter juga menerima assistant
prefill `{` dan `session_id` per channel untuk sticky routing serta peluang
prompt-cache hit yang lebih tinggi. Prompt system dibagi menjadi prefix stabil
dan bagian dinamis supaya provider yang mendukung prefix/KV caching dapat
menggunakan ulang prefix yang sama.

Konfigurasi dapat ditambahkan ke `.env`:

```env
LLM_ROUTING_ENABLED=true
LLM_JSON_PREFILL_ENABLED=true
LLM_PROMPT_CACHE_ENABLED=true
LLM_FAST_TIMEOUT_SECONDS=10
LLM_STANDARD_TIMEOUT_SECONDS=20

LLM_FAST_PROVIDER=openrouter
LLM_FAST_MODEL=openai/gpt-4o-mini
LLM_STANDARD_PROVIDER=openrouter
LLM_STANDARD_MODEL=openai/gpt-4o-mini

LLM_COMPLEX_PROVIDER=nvidia_nim
LLM_COMPLEX_MODEL=moonshotai/kimi-k3

LLM_FALLBACK_PROVIDER=openrouter
LLM_FALLBACK_MODEL=openai/gpt-4o-mini
```

Provider fallback hanya diaktifkan jika API key provider tersebut tersedia.
Log `[SENA ROUTER]` menunjukkan tier, model yang dipilih, dan perpindahan
fallback. Log `[SENA CACHE]` menunjukkan token cache OpenRouter jika provider
mengembalikan metrik tersebut.

Semua konfigurasi routing juga tersedia di **AI Setting > Model Routing**:

- enable/disable tiered routing;
- provider dan model FAST;
- provider dan model STANDARD;
- provider dan model COMPLEX;
- provider dan model fallback;
- JSON assistant prefill;
- prompt cache;
- reset ke routing default.

Pilihan **Ikuti Primary** memakai provider dan model utama. Nilai yang diterapkan
dari UI disimpan ke `data/ai_settings.json` dan langsung aktif tanpa restart.
File konfigurasi lama dimigrasikan otomatis dengan default routing yang aman.

## Emoji Manager

Atur lokasi GIF melalui `.env`:

```env
SENA_GIF_FOLDER=D:\Discord GIF
```

Jika dikosongkan, Senna memilih default sesuai platform: `D:\import` pada
Windows, `~/storage/downloads` pada Termux, dan `~/Downloads` pada Linux/macOS.

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

Sena tidak membalas seluruh channel secara otomatis. Discord text memakai short-term context bersama per server dan channel, tetapi identitas setiap pembicara tetap dibedakan memakai Discord user ID. Voice tetap memakai session per user.

1. Mention bot, balas pesan Sena, atau panggil `Sen`/`Sena` di awal pesan untuk mengaktifkan sesi channel.
2. Pesan biasa selama sesi aktif hanya masuk recent context dan tidak otomatis dibalas.
3. Balasan antar-user tanpa mention Sena diabaikan sepenuhnya.
4. Gunakan `@Sena diam`, `@Sena tidur`, `@Sena stop`, `@Sena mute`, `@Sena shut up`, atau `@Sena sleep` untuk membisukan sesi.
5. Gunakan `Sen bangun` atau `@Sena bangun` untuk mengaktifkan kembali sesi.

Sesi ACTIVE kembali menjadi INACTIVE setelah 120 detik tanpa aktivitas. History hanya disimpan di RAM, dibatasi 20 message, dan dihapus saat sesi timeout, dibisukan, atau bot ditutup.

### Owner dan long-term memory

Isi `SENA_OWNER_ID` dengan Discord user ID owner, bukan username atau nickname. Jika kosong atau tidak valid, bot tetap berjalan tetapi fitur owner dan long-term memory dinonaktifkan.

Memory V1 hanya tersedia untuk owner. Sena menganggap owner sebagai ayah dan dirinya sebagai anak perempuan secara natural tanpa menjadikannya sebutan wajib. Memory disimpan secara private di `data/sena_memory.db`; pengguna biasa tidak menerima relationship context atau memory tersebut.

Perintah eksplisit yang didukung:

- `Sen ingat bahwa gue lebih suka Python`
- `Sen simpan ini project gue namanya Sena`
- `Sen lupakan gue suka Valorant`
- `Sen hapus ingatan tentang Valorant`

Hanya pesan yang benar-benar memicu respons yang melakukan retrieval memory. Pesan `IGNORE` dan `CONTEXT_ONLY` tidak membaca atau menulis database. Retrieval dibatasi maksimal lima memory dan 2.500 karakter.

### Expression System

Setiap balasan Discord Sena mendapat tepat satu primary emoji. Jika custom emoji katalog tidak tersedia, bot otomatis memakai Unicode yang sesuai dengan emotion hasil AI. Sticker dan GIF hanya bonus, mempunyai intensity threshold serta cooldown, dan kegagalannya tidak membatalkan text+emoji yang sudah terkirim.

Katalog berada di `config/expressions.json`. Model AI hanya memilih `emotion`, `intent`, `intensity`, dan preferensi bonus; Discord ID dan path media hanya boleh berasal dari katalog lokal. Tambahkan GIF ke `assets/expressions/gifs/`, lalu gunakan path relatif terhadap folder tersebut pada field `local_path`.

Contoh custom emoji:

```json
{
  "key": "senna_smug_soft_01",
  "name": "senna_smug",
  "discord_id": 123456789012345678,
  "guild_id": 111111111111111111,
  "animated": false,
  "emotion": "smug",
  "intents": ["playful_teasing", "reaction"],
  "intensity_min": 0.2,
  "intensity_max": 0.65,
  "tags": ["smirk", "teasing"],
  "enabled": true,
  "owner_affinity": 0.1,
  "priority": 1.0
}
```

Masukkan object tersebut ke array `emojis`. Catalog rusak saat startup menghasilkan Unicode-only mode; reload yang rusak mempertahankan catalog lama.

Personality Phase 2 aktif berada di:

```text
config/personality.json
```

File JSON tersebut mengatur identity, tone, energy, humor, friendliness, formality, panjang respons, penggunaan emoji, bahasa, trait level 0–10, helping style, roughness rules, adaptasi konteks, dan behavior percakapan. Bagian `speech` menyimpan preferred expressions serta contoh praise/correction untuk integrasi respons lanjutan. Nilainya dapat diedit melalui **AI Settings > Personality Settings** atau langsung di file lalu memilih **Reload personality**. Nilai tidak dikenal menggunakan default yang aman tanpa mematikan bot. Kebijakan bahasa default adalah `auto`, sehingga Sena mengikuti bahasa pesan terbaru secara natural.

## Voice System dan Terminal TTS Queue

1. Pilih **Voice**.
2. Pilih server.
3. Pilih voice channel.
4. Pilih **Join VC**.
5. Pilih **Terminal TTS** lalu **Kirim TTS / Queue**.
6. Ketik teks yang ingin diucapkan bot.

Contoh:

```text
TTS > halo semuanya
QUEUE > ditambahkan, menunggu=1

VOICE [1] > mulai berbicara
VOICE [1] > selesai
```

Anda dapat terus menambahkan teks saat bot berbicara. Audio diproses satu per satu. Ketik `exit` untuk menunggu antrean selesai dan kembali.
Ketik `status` untuk melihat jumlah antrean atau `clear` untuk menghapus audio yang belum diputar.

## Speech-to-Text Discord VC

Voice System dapat menerima audio setiap user secara terpisah menggunakan `discord-ext-voice-recv`, memotong utterance dengan VAD, lalu mentranskripsikannya menggunakan Faster Whisper.

1. Buka **Voice > Connect / Change VC**.
2. Buka **Voice > STT**.
3. Aktifkan **STT ON/OFF**.
4. Tunggu model Faster Whisper selesai diunduh saat transkripsi pertama.
5. Ucapkan `Sen`, `Sena`, atau wake alias lain diikuti pertanyaan.

Setelah session ACTIVE, percakapan dapat dilanjutkan tanpa wake word selama timeout belum tercapai. Ucapkan `Sen diam` untuk membuat session user menjadi SILENCED, lalu panggil Sena lagi untuk mengaktifkannya.

Mode yang tersedia:

- `wake_word`: mode default; hanya percakapan yang dibangunkan yang masuk AI.
- `always_active`: semua utterance masuk AI, cocok untuk VC privat.
- `test_only`: transcript hanya ditampilkan di terminal.

Pengaturan STT disimpan di `data/stt_settings.json`. Audio diproses di RAM dan tidak disimpan. Model default adalah `small` pada CPU `int8`; model dapat diganti dari menu STT. Gunakan **Test STT satu utterance** untuk memeriksa receiver dan transkripsi tanpa mengirim hasil ke AI.

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

1. Buka **Voice > Voice Changer > Model Manager**.
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

Pengaturan voice output otomatis disimpan ke:

```text
data/voice_settings.json
```

Nilai berikut dipulihkan ketika menu Voice dibuka kembali atau bot direstart:

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
