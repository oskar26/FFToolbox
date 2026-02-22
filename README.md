# 🎬 fftoolbox Pro

**Smart terminal video converter powered by FFmpeg — v1.0**

Convert, compress, and re-encode videos from the command line with a beautiful interactive interface. No cryptic flags needed — just pick a preset and go.

Built to solve a real problem: **DaVinci Resolve exports a 3-minute 4K video as a 10 GB ProRes file. fftoolbox turns it into a 200 MB H.264 file in a few minutes, ready to send on WhatsApp or upload anywhere.**

---

## ✨ Features

- **Interactive file browser** — navigate your filesystem, select single files or batch-select entire folders (with optional recursive search)
- **13 smart presets** covering every common use case
- **Real-time progress bar** with speed (e.g. `3.2×`) and ETA
- **Two-pass encoding** for precise file size targeting
- **Hardware encoder detection** — automatically finds NVENC, VAAPI, QuickSync, AMF, VideoToolbox
- **Auto-suggests the best preset** based on source codec, file size, and resolution
- **Batch processing** — convert entire folders in one run
- **Detailed file info** — codec, resolution, FPS, bitrate, duration shown before encoding
- **Post-encode feedback** — exact size difference, percentage saved, WhatsApp compatibility check
- **Collision-safe output** — never overwrites existing files

---

## 📦 Installation

### Requirements

- Python 3.8 or newer
- `ffmpeg` and `ffprobe` in your PATH

**Install ffmpeg:**
```bash
# Ubuntu / Debian
sudo apt install ffmpeg

# Arch Linux
sudo pacman -S ffmpeg

# macOS
brew install ffmpeg

# Windows
# Download from https://ffmpeg.org/download.html and add to PATH
```

The `rich` library for the terminal UI is **auto-installed** on first run.

### Install as a system command (Linux / macOS)

```bash
# Clone or download the script
git clone https://github.com/yourusername/fftoolbox.git
cd fftoolbox

# Make it executable
chmod +x fftoolbox_pro.py

# Install system-wide
sudo cp fftoolbox_pro.py /usr/local/bin/fftoolbox
sudo chmod +x /usr/local/bin/fftoolbox

# Now run from anywhere
fftoolbox
```

### Or run directly

```bash
python3 fftoolbox_pro.py
```

---

## 🚀 Usage

Just run it — everything else is interactive:

```bash
fftoolbox
```

You will be guided through 6 steps:

1. **Select file(s)** — browse interactively, paste a path, or point to a directory
2. **Choose a preset** — the tool suggests the best one based on your source
3. **Configure** — some presets ask follow-up questions (target size, resolution, etc.)
4. **Set output folder** — beside source, Desktop, or custom path
5. **Review the encode plan** — see all files, sizes, durations before committing
6. **Encode** — watch the live progress bar, see size savings when done

---

## 🎛️ Presets

### 📤 Sharing
| Preset | Description |
|--------|-------------|
| 📱 **WhatsApp** | Two-pass to stay under 100 MB · 720p max · H.264 · universal compat |
| ✈️ **Telegram** | 1080p · CRF 22 · AAC 192 kb/s · Telegram supports up to 2 GB |

> **WhatsApp limits:** Videos sent as media (with preview/autoplay) are capped at **100 MB** at 720p. You can send files up to **2 GB** by attaching them as a document (no preview). fftoolbox covers both workflows.

### 🎬 Professional
| Preset | Description |
|--------|-------------|
| 🎬 **DaVinci Resolve Cleanup** | ProRes / DNxHR → H.264 · CRF 18 · near-lossless · shrinks 10 GB to ~200–800 MB |
| 🗄️ **Archive H.265** | CRF 18 · ~40 % smaller than H.264 · Apple HVC1 tag · long-term storage |

### 🌐 Web
| Preset | Description |
|--------|-------------|
| 🌐 **Web / Social Media** | H.264 · CRF 23 · 1080p max · fast-start · YouTube / Vimeo / Instagram |

### 📦 Compression
| Preset | Description |
|--------|-------------|
| 🟢 **Compress Light** | CRF 20 · ~25 % smaller · barely noticeable quality loss |
| 🟡 **Compress Medium** | CRF 26 · ~50 % smaller · noticeable but very watchable |
| 🔴 **Compress Heavy** | CRF 32 · 720p max · ~75 % smaller · clear quality reduction |

### 🎯 Exact Control
| Preset | Description |
|--------|-------------|
| 📐 **Target File Size** | Enter exact MB → two-pass encoding hits the target precisely |
| 📊 **Target % Compression** | Enter what % of original size you want (e.g. 30 %) → auto bitrate |

### ⚡ Utility
| Preset | Description |
|--------|-------------|
| ⚡ **Quick Convert** | H.264 · CRF 23 · medium speed · great for batch jobs |
| 🔊 **Fix Audio** | Video stream copied unchanged · audio → AAC · almost instant |

### ⚙️ Custom
Full manual control over:
- Video codec: H.264, H.265, AV1, VP9, or any detected hardware encoder
- Quality: CRF, target MB, or target % — with two-pass option
- Encode speed: ultrafast → veryslow (9 levels)
- Resolution: 4K / 1440p / 1080p / 720p / 480p / 360p / 240p / 144p / custom
- Audio codec: AAC, Opus, MP3, E-AC3, FLAC, or copy
- Optional: deinterlace, noise reduction, all audio tracks

---

## 🖥️ Supported Resolutions

| Resolution | Dimensions |
|------------|------------|
| 4K UHD     | 3840 × 2160 |
| 1440p      | 2560 × 1440 |
| 1080p      | 1920 × 1080 |
| 720p       | 1280 × 720  |
| 480p       | 854 × 480   |
| 360p       | 640 × 360   |
| 240p       | 426 × 240   |
| 144p       | 256 × 144   |
| Custom     | Enter any width × height |

> fftoolbox never upscales — if you pick a resolution larger than the source, it keeps the original.

---

## 🔧 Hardware Acceleration

fftoolbox automatically detects available hardware encoders:

| Encoder | Platform |
|---------|----------|
| NVIDIA NVENC | Linux / Windows (NVIDIA GPU) |
| VAAPI | Linux (Intel / AMD GPU) |
| Intel QuickSync | Linux / Windows |
| AMD AMF | Windows (AMD GPU) |
| Apple VideoToolbox | macOS |

Hardware encoders appear as options in the **Custom** preset. They encode much faster but may produce slightly larger files than software encoders at the same quality setting.

---

## 📁 Supported Input Formats

`.mp4`, `.mov`, `.mkv`, `.m4v`, `.avi`, `.wmv`, `.flv`, `.webm`, `.mxf`, `.ts`, `.mts`, `.m2ts`, `.mpg`, `.mpeg`, `.3gp`, `.ogv`, `.dv`, `.vob`

Output is always `.mp4` (H.264/H.265) for maximum compatibility.

---

## 💡 Common Workflows

### DaVinci Resolve 4K export → WhatsApp
```
Run fftoolbox
Select your .mov / .mp4 export
Preset: WhatsApp (suggested automatically)
Done — output is < 100 MB and plays with preview
```

### Batch compress a folder of videos
```
Run fftoolbox
Choose "Entire directory (batch mode)"
Point to your folder
Preset: Compress Medium
All files are processed, output in fftoolbox_output/
```

### Exact target size for email / upload limit
```
Run fftoolbox
Choose your file
Preset: Target File Size
Enter e.g. 25 MB
Two-pass encoding hits the mark
```

### Fix audio codec incompatibility
```
Run fftoolbox
Select the problem file
Preset: Fix Audio
Video is copied unchanged, audio is reencoded to AAC — done in seconds
```

---

## 🐧 Platform Notes

- **Linux** — fully supported. VAAPI hardware encoding available on Intel/AMD.
- **macOS** — fully supported. VideoToolbox available on Apple Silicon and Intel Macs.
- **Windows** — run with `python3 fftoolbox_pro.py` in a terminal. NVENC / AMF supported.

---

## 📄 License

MIT — free to use, modify, and distribute.

---

## 🤝 Contributing

Pull requests welcome! Ideas for future versions:
- Subtitle stream handling
- Chapter preservation
- HDR → SDR tone mapping
- Watch folder / daemon mode
- Config file for saved preferences

---

*fftoolbox Pro v1.0 · Built with Python + FFmpeg + rich*
