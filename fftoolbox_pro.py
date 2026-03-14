#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║           fftoolbox Pro  v1.3  —  Smart Media Converter          ║
║  Video · Audio Extraction · Audio Conversion · DaVinci Fix       ║
╚══════════════════════════════════════════════════════════════════╝

Install as system command:
  sudo cp fftoolbox_pro.py /usr/local/bin/fftoolbox
  sudo chmod +x /usr/local/bin/fftoolbox
  fftoolbox

Requirements: Python 3.8+  ·  ffmpeg + ffprobe in PATH
License: MIT  ·  https://github.com/oskar26/FFToolbox
"""

import sys, os, re, json, time, shutil, tempfile, subprocess, traceback, threading
from pathlib import Path
from datetime import timedelta
from typing import Optional, List, Tuple, Dict, Any
from urllib.request import urlopen, Request
from urllib.error import URLError
from copy import deepcopy

# ── auto-install rich ────────────────────────────────────────────────────────
def _ensure_rich():
    try:
        import rich
    except ImportError:
        print("⚙  Installing 'rich' for beautiful UI …")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install",
                                   "rich", "--quiet", "--break-system-packages"],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install",
                                       "rich", "--quiet"],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:
                print(f"ERROR: pip install rich failed: {e}\nRun: pip install rich")
                sys.exit(1)
        print("✓  Done.\n")
_ensure_rich()

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.rule import Rule
from rich.progress import (Progress, BarColumn, TextColumn,
                           TaskProgressColumn, SpinnerColumn, TimeElapsedColumn)
from rich.prompt import Prompt, Confirm
from rich.columns import Columns
from rich import box
from rich.align import Align
from rich.markup import escape
from rich.text import Text

console = Console(highlight=False)

# ════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ════════════════════════════════════════════════════════════════════════

APP_VERSION     = "1.3"
APP_NAME        = "fftoolbox"
GITHUB_OWNER    = "oskar26"
GITHUB_REPO     = "FFToolbox"
GITHUB_BRANCH   = "main"
GITHUB_API_URL  = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
GITHUB_RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}/{GITHUB_BRANCH}"
GITHUB_SCRIPT   = f"{GITHUB_RAW_BASE}/fftoolbox_pro.py"
CONFIG_DIR      = Path.home() / ".config" / "fftoolbox"
PRESETS_DIR    = CONFIG_DIR / "presets"
HISTORY_FILE   = CONFIG_DIR / "history.json"
BITRATE_SAFETY = 0.94   # 94% — ensures output is always UNDER user's target

WHATSAPP_MB    = 100
TELEGRAM_MB    = 2048

VIDEO_EXTENSIONS = {
    ".mp4",".mov",".mkv",".m4v",".avi",".wmv",".flv",".webm",
    ".mxf",".ts",".mts",".m2ts",".mpg",".mpeg",".3gp",".ogv",
    ".dv",".vob",".f4v",".rmvb",".asf",
}
AUDIO_EXTENSIONS = {
    ".mp3",".aac",".flac",".wav",".ogg",".opus",".m4a",
    ".wma",".aiff",".aif",".ape",".mka",".ac3",".eac3",
}
ALL_MEDIA = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS

PROFESSIONAL_CODECS = {
    "prores","prores_ks","dnxhd","dnxhr","mjpeg","v210",
    "r10k","r210","cineform","cfhd","huffyuv","ffv1","utvideo",
}

RESOLUTIONS = [
    (None,  None,  "Keep original"),
    (3840,  2160,  "4K UHD   (3840 × 2160)"),
    (2560,  1440,  "1440p    (2560 × 1440)"),
    (1920,  1080,  "1080p    (1920 × 1080)"),
    (1280,  720,   "720p     (1280 × 720)"),
    (854,   480,   "480p     (854 × 480)"),
    (640,   360,   "360p     (640 × 360)"),
    (426,   240,   "240p     (426 × 240)"),
    (256,   144,   "144p     (256 × 144)"),
]

AUDIO_FORMATS = {
    "mp3":  {"codec":"libmp3lame", "ext":".mp3", "label":"MP3  — universal compatibility"},
    "aac":  {"codec":"aac",        "ext":".m4a", "label":"AAC  — great quality, small size"},
    "flac": {"codec":"flac",       "ext":".flac","label":"FLAC — lossless, large files"},
    "opus": {"codec":"libopus",    "ext":".opus","label":"Opus — best quality/size ratio (modern)"},
    "wav":  {"codec":"pcm_s16le",  "ext":".wav", "label":"WAV  — uncompressed, DaVinci friendly"},
    "ogg":  {"codec":"libvorbis",  "ext":".ogg", "label":"OGG  — open source, good quality"},
}

# ════════════════════════════════════════════════════════════════════════
# VIDEO PRESETS
# ════════════════════════════════════════════════════════════════════════

PRESETS: Dict[str, Dict[str, Any]] = {

    # ── Smart ────────────────────────────────────────────────────────────
    "smart": {
        "group":"⭐  Smart","name":"Smart Auto (analyzes your video)","emoji":"🧠",
        "desc":"Analyzes codec · bitrate · resolution → computes ideal CRF + resolution",
        "codec":"libx264","crf":None,"speed":"slow","audio_codec":"aac","audio_kbps":128,
        "max_res":None,"target_mb":None,"two_pass":False,"color":"bold cyan",
        "tip":"Best all-round choice. Analyzes your specific video before encoding.",
    },

    # ── DaVinci Resolve ──────────────────────────────────────────────────
    "resolve_audio_fix": {
        "group":"🎬  DaVinci Resolve","name":"DaVinci Resolve — Fix Audio (Linux)","emoji":"🔧",
        "desc":"Copies video · converts audio → PCM 48 kHz (fixes Resolve Linux import bug)",
        "codec":"copy","crf":None,"speed":None,"audio_codec":"pcm_s16le","audio_kbps":None,
        "max_res":None,"target_mb":None,"two_pass":False,"color":"bold yellow",
        "tip":"Resolve on Linux often rejects AAC/Opus audio. This converts to PCM — the fix.",
        "_resolve_fix":True,"_output_ext":".mov",
    },
    "resolve_cleanup": {
        "group":"🎬  DaVinci Resolve","name":"DaVinci Resolve — Cleanup Export","emoji":"🎬",
        "desc":"ProRes / DNxHR → H.264 · CRF 18 · near-lossless · keeps original resolution",
        "codec":"libx264","crf":18,"speed":"slow","audio_codec":"aac","audio_kbps":192,
        "max_res":None,"target_mb":None,"two_pass":False,"color":"cyan",
        "tip":"Shrinks a 10 GB ProRes export to ~200–800 MB without visible quality loss.",
    },
    "resolve_import_ready": {
        "group":"🎬  DaVinci Resolve","name":"DaVinci Resolve — Import Ready","emoji":"📥",
        "desc":"H.264 + PCM 48 kHz in MOV container · maximally compatible with Resolve Linux",
        "codec":"libx264","crf":18,"speed":"slow","audio_codec":"pcm_s16le","audio_kbps":None,
        "max_res":None,"target_mb":None,"two_pass":False,"color":"bright_cyan",
        "tip":"Use this to prepare any video for editing in DaVinci Resolve on Linux.",
        "_output_ext":".mov",
    },

    # ── Sharing ──────────────────────────────────────────────────────────
    "whatsapp": {
        "group":"📤  Sharing","name":"WhatsApp  (< 100 MB, 720p)","emoji":"📱",
        "desc":"Two-pass · 94% safety margin · 720p max · H.264 · AAC 96 kb/s",
        "codec":"libx264","crf":None,"speed":"slow","audio_codec":"aac","audio_kbps":96,
        "max_res":(1280,720),"target_mb":95,"two_pass":True,"color":"green",
        "tip":"WhatsApp shows video previews up to 100 MB. Two-pass stays safely under.",
    },
    "telegram": {
        "group":"📤  Sharing","name":"Telegram  (1080p, high quality)","emoji":"✈️",
        "desc":"1080p max · H.264 CRF 22 · AAC 192 kb/s · Telegram supports up to 2 GB",
        "codec":"libx264","crf":22,"speed":"slow","audio_codec":"aac","audio_kbps":192,
        "max_res":(1920,1080),"target_mb":None,"two_pass":False,"color":"bright_blue",
        "tip":"Telegram keeps quality intact. Great for high-quality video sharing.",
    },
    "email": {
        "group":"📤  Sharing","name":"Email Attachment  (< 25 MB)","emoji":"📧",
        "desc":"Two-pass · stays under 25 MB · 720p · for email clients with size limits",
        "codec":"libx264","crf":None,"speed":"slow","audio_codec":"aac","audio_kbps":96,
        "max_res":(1280,720),"target_mb":23,"two_pass":True,"color":"bright_green",
        "tip":"Most email providers cap attachments at 25 MB. Two-pass hits the target.",
    },

    # ── Archive / Quality ────────────────────────────────────────────────
    "archive_h264": {
        "group":"🗄️  Archive","name":"Archive H.264  (near-lossless)","emoji":"💎",
        "desc":"CRF 16 · highest H.264 quality · large files · for permanent storage",
        "codec":"libx264","crf":16,"speed":"slow","audio_codec":"aac","audio_kbps":320,
        "max_res":None,"target_mb":None,"two_pass":False,"color":"bright_white",
        "tip":"CRF 16 = near-lossless H.264. Large files but maximum visual fidelity.",
    },
    "archive_h265": {
        "group":"🗄️  Archive","name":"Archive H.265  (~40% smaller than H.264)","emoji":"🗄️",
        "desc":"CRF 18 · HEVC · ~40% smaller than H.264 · Apple HVC1 tag",
        "codec":"libx265","crf":18,"speed":"slow","audio_codec":"aac","audio_kbps":192,
        "max_res":None,"target_mb":None,"two_pass":False,"color":"blue",
        "tip":"Best long-term archive. Supported by all modern devices.",
    },

    # ── Web / Social ─────────────────────────────────────────────────────
    "web_1080p": {
        "group":"🌐  Web & Social","name":"Web / Social 1080p","emoji":"🌐",
        "desc":"H.264 · CRF 23 · 1080p max · fast-start · YouTube / Vimeo / Instagram",
        "codec":"libx264","crf":23,"speed":"slow","audio_codec":"aac","audio_kbps":128,
        "max_res":(1920,1080),"target_mb":None,"two_pass":False,"color":"yellow",
        "tip":"Safe universal choice for any online platform.",
    },
    "web_4k": {
        "group":"🌐  Web & Social","name":"Web 4K (YouTube HDR-ready)","emoji":"🖥️",
        "desc":"H.264 · CRF 18 · 4K · fast-start · high-bitrate for platform re-encoding",
        "codec":"libx264","crf":18,"speed":"slow","audio_codec":"aac","audio_kbps":192,
        "max_res":(3840,2160),"target_mb":None,"two_pass":False,"color":"bright_yellow",
        "tip":"Upload at maximum quality — YouTube / Vimeo will re-encode anyway.",
    },

    # ── Compression ──────────────────────────────────────────────────────
    "compress_light": {
        "group":"📦  Compression","name":"Compress Light  (~25% smaller)","emoji":"🟢",
        "desc":"CRF 20 · barely noticeable quality loss",
        "codec":"libx264","crf":20,"speed":"medium","audio_codec":"aac","audio_kbps":192,
        "max_res":None,"target_mb":None,"two_pass":False,"color":"bright_green",
        "tip":"Almost imperceptible quality difference.",
    },
    "compress_medium": {
        "group":"📦  Compression","name":"Compress Medium  (~50% smaller)","emoji":"🟡",
        "desc":"CRF 26 · noticeable but very watchable",
        "codec":"libx264","crf":26,"speed":"medium","audio_codec":"aac","audio_kbps":128,
        "max_res":None,"target_mb":None,"two_pass":False,"color":"yellow",
        "tip":"Good balance of quality and size reduction.",
    },
    "compress_heavy": {
        "group":"📦  Compression","name":"Compress Heavy  (~75% smaller)","emoji":"🔴",
        "desc":"CRF 32 · 720p max · clear quality loss",
        "codec":"libx264","crf":32,"speed":"fast","audio_codec":"aac","audio_kbps":64,
        "max_res":(1280,720),"target_mb":None,"two_pass":False,"color":"red",
        "tip":"Maximum compression. Pixelation may be visible.",
    },

    # ── Exact Control ────────────────────────────────────────────────────
    "target_mb": {
        "group":"🎯  Exact Control","name":"Target Exact Size (MB)","emoji":"📐",
        "desc":"Enter MB → two-pass · 94% safety margin · never exceeds your target",
        "codec":"libx264","crf":None,"speed":"slow","audio_codec":"aac","audio_kbps":128,
        "max_res":None,"target_mb":None,"two_pass":True,"color":"magenta",
        "tip":"Uses 94% safety margin so output is always UNDER your target.",
    },
    "target_percent": {
        "group":"🎯  Exact Control","name":"Target % Compression","emoji":"📊",
        "desc":"Enter what % of original size you want → auto bitrate + two-pass",
        "codec":"libx264","crf":None,"speed":"slow","audio_codec":"aac","audio_kbps":128,
        "max_res":None,"target_mb":None,"two_pass":True,"color":"magenta",
        "tip":"E.g. 30 → output will be ~30% of original file size.",
    },

    # ── Utility ──────────────────────────────────────────────────────────
    "quick": {
        "group":"⚡  Utility","name":"Quick Convert  (medium speed)","emoji":"⚡",
        "desc":"H.264 · CRF 23 · medium speed · any resolution",
        "codec":"libx264","crf":23,"speed":"medium","audio_codec":"aac","audio_kbps":128,
        "max_res":None,"target_mb":None,"two_pass":False,"color":"bright_yellow",
        "tip":"Fast encode with good quality. Great for batch jobs.",
    },
    "fix_audio": {
        "group":"⚡  Utility","name":"Fix Audio  (copy video stream)","emoji":"🔊",
        "desc":"Video copied unchanged · audio → AAC 192 kb/s · almost instant",
        "codec":"copy","crf":None,"speed":None,"audio_codec":"aac","audio_kbps":192,
        "max_res":None,"target_mb":None,"two_pass":False,"color":"white",
        "tip":"Almost instant — only audio is processed. Fixes codec compatibility issues.",
    },
    "strip_audio": {
        "group":"⚡  Utility","name":"Strip Audio  (video only, no sound)","emoji":"🔇",
        "desc":"Remove all audio tracks · video copied unchanged · instant",
        "codec":"copy","crf":None,"speed":None,"audio_codec":None,"audio_kbps":None,
        "max_res":None,"target_mb":None,"two_pass":False,"color":"dim white",
        "tip":"Creates a silent video. Useful for background loops, memes, etc.",
        "_no_audio":True,
    },

    # ── Custom ───────────────────────────────────────────────────────────
    "custom": {
        "group":"⚙️   Custom","name":"Custom — full manual control","emoji":"⚙️",
        "desc":"Configure codec · CRF · speed · resolution · audio · hardware encoders",
        "codec":None,"crf":None,"speed":None,"audio_codec":None,"audio_kbps":None,
        "max_res":None,"target_mb":None,"two_pass":False,"color":"dim white",
        "tip":"Full manual control over every encoding parameter.",
    },
}

# ════════════════════════════════════════════════════════════════════════
# HISTORY / RECENT FILES
# ════════════════════════════════════════════════════════════════════════

def load_history() -> Dict[str, Any]:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if HISTORY_FILE.exists():
            return json.loads(HISTORY_FILE.read_text())
    except Exception:
        pass
    return {"recent_files": [], "recent_dirs": [], "last_output_dir": None}

def save_history(h: Dict[str, Any]) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        HISTORY_FILE.write_text(json.dumps(h, indent=2))
    except Exception:
        pass

def add_to_history(h: Dict[str, Any], files: List[str], output_dir: str) -> None:
    for f in files:
        d = str(Path(f).parent)
        if d not in h["recent_dirs"]:
            h["recent_dirs"].insert(0, d)
        if f not in h["recent_files"]:
            h["recent_files"].insert(0, f)
    h["recent_dirs"]  = h["recent_dirs"][:10]
    h["recent_files"] = h["recent_files"][:20]
    h["last_output_dir"] = output_dir
    save_history(h)

# ════════════════════════════════════════════════════════════════════════
# SYSTEM / FFPROBE HELPERS
# ════════════════════════════════════════════════════════════════════════

def check_deps() -> Tuple[bool, bool]:
    return bool(shutil.which("ffmpeg")), bool(shutil.which("ffprobe"))

def run_ffprobe(path: str) -> Optional[dict]:
    cmd = ["ffprobe","-v","error","-print_format","json",
           "-show_format","-show_streams",path]
    try:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           check=True, text=True, timeout=30)
        return json.loads(r.stdout)
    except subprocess.TimeoutExpired:
        console.print("[red]  ffprobe timed out[/]"); return None
    except (json.JSONDecodeError, subprocess.CalledProcessError) as e:
        console.print(f"[red]  ffprobe error: {str(e)[:100]}[/]"); return None

def video_stream(info: dict) -> Optional[dict]:
    for s in info.get("streams",[]):
        if s.get("codec_type") == "video": return s
    return None

def audio_stream(info: dict) -> Optional[dict]:
    for s in info.get("streams",[]):
        if s.get("codec_type") == "audio": return s
    return None

def all_audio_streams(info: dict) -> List[dict]:
    return [s for s in info.get("streams",[]) if s.get("codec_type") == "audio"]

def subtitle_streams(info: dict) -> List[dict]:
    return [s for s in info.get("streams",[]) if s.get("codec_type") == "subtitle"]

def file_duration(info: dict) -> float:
    vs = video_stream(info)
    if vs:
        try: return float(vs["duration"])
        except: pass
    try: return float(info.get("format",{}).get("duration") or 0)
    except: return 0.0

def file_size_bytes(info: dict) -> int:
    try: return int(info.get("format",{}).get("size") or 0)
    except: return 0

def is_audio_only(info: dict) -> bool:
    return video_stream(info) is None and audio_stream(info) is not None

def is_professional(info: dict) -> bool:
    vs = video_stream(info)
    vc = (vs or {}).get("codec_name","").lower()
    return any(p in vc for p in PROFESSIONAL_CODECS)

def safe_int(val, default=0) -> int:
    try: return int(val)
    except: return default

def safe_float(val, default=0.0) -> float:
    try: return float(val)
    except: return default

def human_size(b: float) -> str:
    for u in ["B","KB","MB","GB","TB"]:
        if abs(b) < 1024.0: return f"{b:6.1f} {u}"
        b /= 1024.0
    return f"{b:.1f} PB"

def human_dur(secs: float) -> str:
    if secs <= 0: return "0:00:00"
    return str(timedelta(seconds=int(secs)))

def fps_str(vs: dict) -> str:
    raw = vs.get("r_frame_rate","")
    try:
        n, d = raw.split("/")
        return f"{int(n)/int(d):.3g} fps"
    except: return raw or "?"

def scale_vf(src_w: int, src_h: int, max_res: Tuple[int,int]) -> Optional[str]:
    mw, mh = max_res
    if src_w <= mw and src_h <= mh: return None
    ratio = min(mw/src_w, mh/src_h)
    nw = (int(src_w*ratio)//2)*2
    nh = (int(src_h*ratio)//2)*2
    return f"scale={nw}:{nh}:flags=lanczos"

def target_video_kbps(target_mb: float, duration_s: float,
                      audio_kbps: int, safety: float = BITRATE_SAFETY) -> int:
    bits   = target_mb * 8 * 1024 * 1024 * safety
    return max(80, int(bits / max(duration_s, 1) / 1000 - audio_kbps))

def parse_progress_time(line: str) -> Optional[float]:
    m = re.search(r"time=(\d+):(\d+):([\d.]+)", line)
    if m: return int(m.group(1))*3600 + int(m.group(2))*60 + float(m.group(3))
    return None

# ════════════════════════════════════════════════════════════════════════
# HARDWARE ENCODER DETECTION + FALLBACK
# ════════════════════════════════════════════════════════════════════════

_HW_CACHE: Optional[List[Tuple[str,str]]] = None

def detect_hw_encoders() -> List[Tuple[str,str]]:
    global _HW_CACHE
    if _HW_CACHE is not None: return _HW_CACHE
    candidates = [
        ("h264_nvenc","NVIDIA NVENC H.264"),("hevc_nvenc","NVIDIA NVENC H.265"),
        ("h264_vaapi","VAAPI H.264 (Intel/AMD)"),("hevc_vaapi","VAAPI H.265 (Intel/AMD)"),
        ("h264_qsv","Intel QuickSync H.264"),("hevc_qsv","Intel QuickSync H.265"),
        ("h264_amf","AMD AMF H.264"),("hevc_amf","AMD AMF H.265"),
        ("h264_videotoolbox","Apple VideoToolbox H.264"),
        ("hevc_videotoolbox","Apple VideoToolbox H.265"),
    ]
    try:
        r = subprocess.run(["ffmpeg","-hide_banner","-encoders"],
                           stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=5)
        out = r.stdout
        _HW_CACHE = [(e,l) for e,l in candidates if e in out]
    except: _HW_CACHE = []
    return _HW_CACHE

def hw_fallback(codec: str, input_path: str) -> str:
    """Test HW encoder; fallback to libx264/libx265 if it fails."""
    HW = {"nvenc","vaapi","qsv","videotoolbox","amf"}
    if not any(h in codec for h in HW): return codec
    console.print(f"  [dim]Testing {codec} …[/]", end="")
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tf: tmp = tf.name
    try:
        r = subprocess.run(
            ["ffmpeg","-hide_banner","-y","-i",input_path,"-t","1",
             "-vf","scale=320:180","-c:v",codec,"-an",tmp],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        if r.returncode == 0:
            console.print(" [green]OK[/]"); return codec
        raise RuntimeError()
    except Exception:
        fb = "libx265" if "hevc" in codec else "libx264"
        console.print(f" [yellow]failed → {fb}[/]"); return fb
    finally:
        try: os.unlink(tmp)
        except: pass

# ════════════════════════════════════════════════════════════════════════
# SMART PRESET ANALYSIS
# ════════════════════════════════════════════════════════════════════════

def compute_smart_preset(info: dict) -> dict:
    preset = deepcopy(PRESETS["smart"])
    vs     = video_stream(info)
    dur    = file_duration(info)
    sz     = file_size_bytes(info)
    src_w  = safe_int((vs or {}).get("width",  1920))
    src_h  = safe_int((vs or {}).get("height", 1080))
    src_bps = safe_int((vs or {}).get("bit_rate")) or (sz*8/max(dur,1))
    src_kbps = src_bps / 1000
    pixels   = max(src_w * src_h, 1)
    bpp      = src_kbps / pixels  # bits per pixel per second

    # CRF based on how compressed the source already is
    if bpp > 0.5:   crf = 18    # very uncompressed (ProRes/raw)
    elif bpp > 0.1: crf = 20
    elif bpp > 0.04: crf = 22
    elif bpp > 0.02: crf = 24
    else:           crf = 26    # already heavily compressed

    # Resolution recommendation
    rec_res = None
    reason  = ""
    if src_w >= 3840 and bpp < 0.05:
        rec_res = (1920,1080); reason = "4K @ low bitrate → 1080p"
    elif src_w >= 2560 and bpp < 0.04:
        rec_res = (1920,1080); reason = "1440p @ low bitrate → 1080p"
    elif src_w >= 1920 and src_kbps < 1500:
        rec_res = (1280,720);  reason = "1080p @ low bitrate → 720p"

    # Estimate output size
    est_ratio = 0.55 * (0.75 ** (crf - 18))
    est_kbps  = src_kbps * est_ratio
    est_mb    = est_kbps * 1000 * dur / (8*1024*1024) if dur > 0 else 0

    rows = [
        ("Source bitrate",     f"{src_kbps:.0f} kb/s"),
        ("Bits/pixel/s",       f"{bpp:.5f}"),
        ("Chosen CRF",         f"{crf}"),
        ("Resolution",         reason if reason else "keep original"),
        ("Estimated output",   f"~{est_mb:.0f} MB" if est_mb > 0 else "unknown"),
    ]
    tbl = Table(box=box.ROUNDED, border_style="dim", show_header=False, padding=(0,1))
    tbl.add_column("K", style="cyan", width=18); tbl.add_column("V")
    for k, v in rows: tbl.add_row(k, v)
    console.print(Panel(tbl, title="[bold]Smart Analysis[/]", border_style="cyan"))

    preset["crf"]       = crf
    preset["max_res"]   = rec_res
    preset["speed"]     = "slow"
    preset["audio_codec"]  = "aac"
    preset["audio_kbps"]   = 128
    return preset

# ════════════════════════════════════════════════════════════════════════
# SMART RESOLUTION RECOMMENDATION
# ════════════════════════════════════════════════════════════════════════

def recommend_resolution(target_mb: float, duration_s: float,
                         audio_kbps: int, src_w: int, src_h: int
                         ) -> Tuple[Optional[Tuple[int,int]], str]:
    if duration_s <= 0: return None, "unknown duration"
    vkbps = target_video_kbps(target_mb, duration_s, audio_kbps)
    thresholds = [
        (3840,2160,8000,"4K"),(2560,1440,4000,"1440p"),
        (1920,1080,1500,"1080p"),(1280,720,500,"720p"),
        (854,480,200,"480p"),(640,360,100,"360p"),
    ]
    for w, h, min_k, label in thresholds:
        if vkbps >= min_k and src_w >= w and src_h >= h:
            res = (w,h) if (w < src_w or h < src_h) else None
            return res, f"~{vkbps} kb/s → [bold]{label}[/] recommended"
    return (640,360), f"~{vkbps} kb/s very low → [yellow]360p[/] minimum"

# ════════════════════════════════════════════════════════════════════════
# PREVIEW ENCODE (5-second test clip with PSNR)
# ════════════════════════════════════════════════════════════════════════

def run_preview(input_path: str, preset: dict, info: dict) -> bool:
    dur   = file_duration(info)
    vs    = video_stream(info)
    src_w = safe_int((vs or {}).get("width",1920))  if vs else 1920
    src_h = safe_int((vs or {}).get("height",1080)) if vs else 1080

    start  = max(0.0, dur * 0.3)
    length = min(5.0, max(1.0, dur * 0.1))
    if length < 0.5:
        console.print("  [dim]Video too short for preview.[/]"); return True

    console.print(f"\n  [bold cyan]Preview Encode[/]  [dim]({length:.0f}s starting at {human_dur(start)})[/]")
    tmpdir = tempfile.mkdtemp(prefix="fftoolbox_prev_")
    tmp_out = os.path.join(tmpdir, "preview.mp4")
    tmp_ref = os.path.join(tmpdir, "reference.mp4")

    try:
        p2 = deepcopy(preset)
        p2["two_pass"] = False
        if p2.get("target_mb"): p2["crf"] = 23; p2["target_mb"] = None

        vf_list = build_vf_list(p2, src_w, src_h)
        co = p2.get("codec") or "libx264"
        if co in ("copy", None): co = "libx264"; p2["crf"] = 22

        cmd = ["ffmpeg","-hide_banner","-y","-ss",str(start),"-t",str(length),"-i",input_path]
        if vf_list: cmd += ["-vf", ",".join(vf_list)]
        cmd += ["-map","0:v","-map","0:a?"]

        if co == "libx264":
            cmd += ["-c:v","libx264","-profile:v","high","-pix_fmt","yuv420p"]
        elif co == "libx265":
            cmd += ["-c:v","libx265","-pix_fmt","yuv420p"]
        else:
            cmd += ["-c:v",co,"-pix_fmt","yuv420p"]

        cmd += ["-crf", str(p2.get("crf",23))]
        sp = p2.get("speed") or "fast"
        HW = {"nvenc","vaapi","qsv","videotoolbox","amf"}
        if not any(h in co for h in HW): cmd += ["-preset", sp]

        ac = p2.get("audio_codec") or "aac"
        ab = p2.get("audio_kbps") or 128
        if ac not in ("copy","flac","pcm_s16le","pcm_s24le"):
            cmd += ["-c:a", ac, "-b:a", f"{ab}k"]
        else:
            cmd += ["-c:a", ac]
        cmd += [tmp_out]

        with console.status("[cyan]Encoding preview clip …[/]"):
            r = subprocess.run(cmd, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=120)

        if r.returncode != 0 or not os.path.exists(tmp_out):
            console.print("  [yellow]Preview failed — continuing anyway.[/]"); return True

        prev_sz   = os.path.getsize(tmp_out)
        prev_kbps = prev_sz * 8 / length / 1000

        # Estimate full output
        est_mb = (preset.get("target_mb") or
                  (prev_kbps * 1000 * dur / (8*1024*1024) if dur > 0 else 0))

        # PSNR via ffmpeg (optional)
        psnr_str = ""
        try:
            with console.status("[dim]Computing quality …[/]"):
                ref_cmd = ["ffmpeg","-hide_banner","-y","-ss",str(start),"-t",str(length),
                           "-i",input_path,"-c:v","libx264","-crf","0",
                           "-preset","ultrafast","-an",tmp_ref]
                rr = subprocess.run(ref_cmd, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, timeout=30)
            if rr.returncode == 0:
                pr = subprocess.run(
                    ["ffmpeg","-hide_banner","-i",tmp_out,"-i",tmp_ref,
                     "-lavfi","psnr","-f","null","-"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                    text=True, timeout=30)
                m = re.search(r"average:([\d.]+)", pr.stderr)
                if m:
                    v = float(m.group(1))
                    q = ("[bold green]Excellent[/]" if v >= 45 else
                         "[green]Very Good[/]" if v >= 40 else
                         "[yellow]Good[/]" if v >= 35 else
                         "[yellow]Acceptable[/]" if v >= 30 else
                         "[red]Poor[/]")
                    psnr_str = f"{v:.1f} dB — {q}"
        except Exception: pass

        tbl = Table(box=box.ROUNDED, border_style="dim", show_header=False, padding=(0,1))
        tbl.add_column("K", style="bold cyan", width=20); tbl.add_column("V")
        tbl.add_row("Preview clip",      f"{length:.0f}s")
        tbl.add_row("Preview size",      human_size(prev_sz))
        tbl.add_row("Bitrate (preview)", f"{prev_kbps:.0f} kb/s")
        if est_mb > 0:
            clr = "green" if not preset.get("target_mb") or est_mb <= preset["target_mb"] else "yellow"
            tbl.add_row("Est. full output", f"[{clr}]~{est_mb:.0f} MB[/]")
        if psnr_str:
            tbl.add_row("Quality (PSNR)", psnr_str)
        console.print(Panel(tbl, title="[bold]Preview Result[/]", border_style="cyan"))

        return Confirm.ask("  Proceed with full encode?", default=True)
    except Exception as e:
        console.print(f"  [yellow]Preview error ({e}) — continuing.[/]"); return True
    finally:
        try: shutil.rmtree(tmpdir)
        except: pass

# ════════════════════════════════════════════════════════════════════════
# AUDIO EXTRACTION + CONVERSION
# ════════════════════════════════════════════════════════════════════════

def pick_audio_format() -> Tuple[str, Dict[str, Any]]:
    """Returns (format_key, format_dict)."""
    console.print()
    console.print("[bold cyan]Output Audio Format[/]")
    tbl = Table(box=box.SIMPLE, padding=(0,1), show_header=False)
    tbl.add_column("#", style="bold dim", width=3)
    tbl.add_column("Format")
    tbl.add_column("Recommended quality", style="dim", width=28)
    keys = list(AUDIO_FORMATS.keys())
    guides = {
        "mp3": "128–320 kb/s",
        "aac": "96–256 kb/s",
        "flac":"lossless (no bitrate needed)",
        "opus":"64–192 kb/s (64 = spoken word, 128 = music)",
        "wav": "lossless (no bitrate needed)",
        "ogg": "96–256 kb/s",
    }
    for i, k in enumerate(keys, 1):
        tbl.add_row(str(i), AUDIO_FORMATS[k]["label"], guides.get(k,""))
    console.print(tbl)
    c = Prompt.ask("Format", choices=[str(i) for i in range(1, len(keys)+1)], default="1")
    key = keys[int(c)-1]
    fmt = deepcopy(AUDIO_FORMATS[key])

    if key not in ("flac","wav"):
        console.print(f"  [dim]Guide: {guides.get(key,'')}[/]")
        default_br = {"mp3":"192","aac":"192","opus":"128","ogg":"192"}.get(key,"192")
        fmt["bitrate"] = int(Prompt.ask("Bitrate kb/s", default=default_br))
    else:
        fmt["bitrate"] = None

    return key, fmt

def extract_audio(files: List[str], infos: Dict[str, Optional[dict]],
                  output_dir: str) -> Tuple[int, int]:
    """Extract audio from video files. Returns (success, failed)."""
    _, fmt = pick_audio_format()
    success, failed = 0, 0

    console.print()
    console.print(Rule("[bold cyan]Extracting Audio[/]"))

    for i, fpath in enumerate(files, 1):
        fi = infos.get(fpath) or run_ffprobe(fpath)
        if not fi:
            console.print(f"  [{i}/{len(files)}] [red]Cannot read: {escape(Path(fpath).name)}[/]")
            failed += 1; continue

        as_ = audio_stream(fi)
        if not as_:
            console.print(f"  [{i}/{len(files)}] [yellow]No audio track: {escape(Path(fpath).name)}[/]")
            failed += 1; continue

        out_name = Path(fpath).stem + fmt["ext"]
        out_path = os.path.join(output_dir, out_name)
        out_path = _unique_path(out_path)

        console.print(f"\n  [bold][{i}/{len(files)}][/]  {escape(Path(fpath).name)}")

        dur = file_duration(fi)
        cmd = ["ffmpeg","-hide_banner","-y","-i",fpath,"-vn"]

        co = fmt["codec"]
        if fmt.get("bitrate"):
            cmd += ["-c:a", co, "-b:a", f"{fmt['bitrate']}k"]
        else:
            cmd += ["-c:a", co]
        cmd += ["-ar","48000",out_path]

        ok = run_with_progress(cmd, dur, f"Extract [{i}/{len(files)}]")
        if ok and os.path.exists(out_path):
            src_sz = file_size_bytes(fi)
            dst_sz = os.path.getsize(out_path)
            console.print(f"  [green]OK[/]  {human_size(src_sz)} → [green]{human_size(dst_sz)}[/]  [dim]{escape(out_path)}[/]")
            success += 1
        else:
            failed += 1

    return success, failed

def convert_audio(files: List[str], output_dir: str) -> Tuple[int, int]:
    """Convert audio files to another format."""
    _, fmt = pick_audio_format()
    success, failed = 0, 0

    console.print()
    console.print(Rule("[bold cyan]Converting Audio[/]"))

    for i, fpath in enumerate(files, 1):
        fi = run_ffprobe(fpath)
        if not fi:
            console.print(f"  [{i}/{len(files)}] [red]Cannot read: {escape(Path(fpath).name)}[/]")
            failed += 1; continue

        out_name = Path(fpath).stem + fmt["ext"]
        out_path = os.path.join(output_dir, out_name)
        out_path = _unique_path(out_path)

        console.print(f"\n  [bold][{i}/{len(files)}][/]  {escape(Path(fpath).name)}")
        dur = file_duration(fi)

        cmd = ["ffmpeg","-hide_banner","-y","-i",fpath]
        if fmt.get("bitrate"):
            cmd += ["-c:a", fmt["codec"], "-b:a", f"{fmt['bitrate']}k"]
        else:
            cmd += ["-c:a", fmt["codec"]]
        cmd += ["-ar","48000", out_path]

        ok = run_with_progress(cmd, dur, f"Convert [{i}/{len(files)}]")
        if ok and os.path.exists(out_path):
            src_sz = file_size_bytes(fi)
            dst_sz = os.path.getsize(out_path)
            console.print(f"  [green]OK[/]  {human_size(src_sz)} → [green]{human_size(dst_sz)}[/]  [dim]{escape(out_path)}[/]")
            success += 1
        else:
            failed += 1

    return success, failed

# ════════════════════════════════════════════════════════════════════════
# PRESET IMPORT / EXPORT
# ════════════════════════════════════════════════════════════════════════

def export_preset(preset: dict, name: str) -> None:
    PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w\-]","_",name.strip())
    path = PRESETS_DIR / f"{safe}.json"
    data = {k: v for k, v in preset.items() if not k.startswith("_")}
    data["_fftoolbox_version"] = APP_VERSION
    data["_export_name"]       = name
    path.write_text(json.dumps(data, indent=2))
    console.print(f"  [green]Preset saved:[/] [dim]{path}[/]")

def import_preset_menu() -> Optional[Dict[str, Any]]:
    PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(PRESETS_DIR.glob("*.json"))
    if not files:
        console.print(f"  [dim]No saved presets in {PRESETS_DIR}[/]"); return None
    console.print("\n[bold cyan]Saved Presets[/]")
    tbl = Table(box=box.SIMPLE, padding=(0,1), show_header=False)
    tbl.add_column("#", style="bold dim", width=3)
    tbl.add_column("Name"); tbl.add_column("Details", style="dim")
    for i, f in enumerate(files, 1):
        try:
            d = json.loads(f.read_text())
            detail = f"codec={d.get('codec','?')} crf={d.get('crf','?')}"
        except: detail = "?"
        tbl.add_row(str(i), d.get("_export_name", f.stem), detail)
    console.print(tbl)
    c = Prompt.ask("Load #", choices=[str(i) for i in range(1,len(files)+1)])
    try:
        loaded = json.loads(files[int(c)-1].read_text())
        for key, default in [("name","Imported"),("emoji","📥"),
                              ("color","white"),("tip","Imported"),("group","Imported")]:
            loaded.setdefault(key, loaded.get("_export_name", default))
        console.print(f"  [green]Loaded: {loaded.get('_export_name','?')}[/]")
        return loaded
    except Exception as e:
        console.print(f"[red]  Failed: {e}[/]"); return None

# ════════════════════════════════════════════════════════════════════════
# AUTO-UPDATER (background)
# ════════════════════════════════════════════════════════════════════════


# ════════════════════════════════════════════════════════════════════════
# AUTO-UPDATER
# ════════════════════════════════════════════════════════════════════════

class UpdateInfo:
    """Holds the result of an update check (filled by background thread)."""
    available:    bool          = False
    remote_ver:   str           = ""
    changelog:    str           = ""
    download_url: str           = ""
    error:        Optional[str] = None

_update_info = UpdateInfo()


def _version_tuple(v: str) -> Tuple[int, ...]:
    """Convert '1.2.3' → (1, 2, 3) for comparison."""
    try:
        return tuple(int(x) for x in re.split(r"[.\-]", v.lstrip("v")) if x.isdigit())
    except Exception:
        return (0,)


def _fetch_update_info() -> None:
    """Background thread: query GitHub Releases API and fill _update_info."""
    global _update_info
    try:
        req = Request(
            GITHUB_API_URL,
            headers={
                "User-Agent":  f"fftoolbox/{APP_VERSION}",
                "Accept":      "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urlopen(req, timeout=4) as r:
            data = json.loads(r.read().decode())

        tag          = data.get("tag_name", "").lstrip("v")
        body         = data.get("body",     "")   # release notes / changelog
        assets       = data.get("assets",   [])

        # Look for a .py asset first, fall back to raw GitHub URL
        script_asset = next(
            (a["browser_download_url"] for a in assets
             if a.get("name","").endswith(".py")),
            GITHUB_SCRIPT,
        )

        if tag and _version_tuple(tag) > _version_tuple(APP_VERSION):
            _update_info.available    = True
            _update_info.remote_ver   = tag
            _update_info.changelog    = body.strip()
            _update_info.download_url = script_asset

    except URLError:
        pass   # no network — silently skip
    except Exception as e:
        _update_info.error = str(e)


def _start_update_check() -> None:
    threading.Thread(target=_fetch_update_info, daemon=True).start()


def show_update_banner() -> None:
    """Called after banner — shows a notice if an update is waiting."""
    if not _update_info.available:
        return

    lines = [
        f"[bold yellow]Update available:[/] v{_update_info.remote_ver}  "
        f"[dim](you have v{APP_VERSION})[/]",
    ]
    if _update_info.changelog:
        # Show first 3 non-empty lines of release notes
        notes = [l for l in _update_info.changelog.splitlines() if l.strip()][:3]
        for n in notes:
            lines.append(f"[dim]  {escape(n)}[/]")

    lines.append(f"\n[dim]Run [bold]fftoolbox --update[/] or type [bold]u[/] at the main menu.[/]")
    console.print(Panel("\n".join(lines), border_style="yellow",
                        title="[bold yellow]⬆  Update[/]"))
    console.print()


def perform_update(interactive: bool = True) -> bool:
    """
    Download the latest release script from GitHub and replace the running script.

    Steps:
      1. Download new script to a temp file
      2. Verify it's valid Python (ast.parse)
      3. Check it contains a newer APP_VERSION string
      4. Back up the current script
      5. Replace (handles /usr/local/bin/ via sudo if needed)
      6. Re-exec the new version

    Returns True if update was applied, False otherwise.
    """
    import ast, stat, hashlib

    url  = _update_info.download_url if _update_info.available else GITHUB_SCRIPT
    ver  = _update_info.remote_ver   if _update_info.available else "latest"

    if interactive:
        console.print()
        console.print(Rule("[bold yellow]⬆  Auto-Updater[/]"))
        console.print(
            f"\n  Downloading [bold]v{ver}[/] from:\n"
            f"  [dim]{url}[/]\n"
        )

        if _update_info.changelog:
            notes = [l for l in _update_info.changelog.splitlines() if l.strip()][:6]
            tbl = Table(box=box.ROUNDED, border_style="dim", show_header=False, padding=(0,1))
            tbl.add_column("", style="dim")
            for n in notes:
                tbl.add_row(escape(n))
            console.print(Panel(tbl, title="[dim]Release Notes[/]", border_style="dim"))

        if not Confirm.ask(f"  Install v{ver} now?", default=True):
            console.print("  [yellow]Update cancelled.[/]")
            return False

    # ── Download ──────────────────────────────────────────────────────
    try:
        console.print("  [dim]Downloading …[/]", end=" ")
        req = Request(url, headers={"User-Agent": f"fftoolbox/{APP_VERSION}"})
        with urlopen(req, timeout=30) as r:
            new_code = r.read()
        console.print("[green]done[/]")
    except Exception as e:
        console.print(f"\n  [red]Download failed: {e}[/]")
        return False

    # ── Verify: valid Python ──────────────────────────────────────────
    try:
        ast.parse(new_code)
    except SyntaxError as e:
        console.print(f"  [red]Downloaded file has syntax error: {e} — aborting.[/]")
        return False

    # ── Verify: contains newer version tag ───────────────────────────
    code_str = new_code.decode("utf-8", errors="replace")
    m = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', code_str)
    if not m:
        console.print("  [red]Cannot find APP_VERSION in downloaded file — aborting.[/]")
        return False
    new_ver_str = m.group(1)
    if _version_tuple(new_ver_str) <= _version_tuple(APP_VERSION):
        console.print(
            f"  [yellow]Downloaded version ({new_ver_str}) is not newer "
            f"than current ({APP_VERSION}) — nothing to do.[/]"
        )
        return False

    # ── SHA256 checksum display ───────────────────────────────────────
    sha256 = hashlib.sha256(new_code).hexdigest()
    console.print(f"  [dim]SHA-256: {sha256[:16]}…[/]")

    # ── Locate the running script ─────────────────────────────────────
    script_path = Path(os.path.abspath(__file__))
    backup_path = script_path.with_suffix(f".v{APP_VERSION}.bak")

    console.print(f"  [dim]Script:  {script_path}[/]")
    console.print(f"  [dim]Backup:  {backup_path}[/]")

    # ── Write to temp file ────────────────────────────────────────────
    with tempfile.NamedTemporaryFile(delete=False, suffix=".py") as tf:
        tf.write(new_code)
        tmp_path = tf.name

    # ── Replace — handle read-only locations (e.g. /usr/local/bin) ───
    def _try_replace() -> bool:
        try:
            shutil.copy2(script_path, backup_path)   # backup
            shutil.move(tmp_path, script_path)       # replace
            os.chmod(script_path,
                     os.stat(script_path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            return True
        except PermissionError:
            return False

    if not _try_replace():
        # Try sudo cp
        console.print(
            f"\n  [yellow]No write permission to {script_path}.[/]\n"
            "  [dim]Trying with sudo (you may be asked for your password) …[/]"
        )
        try:
            subprocess.run(
                ["sudo", "cp", tmp_path, str(script_path)],
                check=True,
            )
            subprocess.run(
                ["sudo", "chmod", "+x", str(script_path)],
                check=True,
            )
            # backup via sudo too
            subprocess.run(
                ["sudo", "cp", str(script_path), str(backup_path)],
                check=False,
            )
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
        except subprocess.CalledProcessError:
            console.print(
                "  [red]sudo failed. Try manually:[/]\n"
                f"  [bold]sudo cp {tmp_path} {script_path}[/]\n"
                f"  [bold]sudo chmod +x {script_path}[/]"
            )
            return False

    console.print(
        f"\n  [bold green]✓  Updated to v{new_ver_str}![/]  "
        f"[dim](backup: {backup_path.name})[/]"
    )

    # ── Re-exec ───────────────────────────────────────────────────────
    console.print("  [dim]Restarting …[/]\n")
    time.sleep(0.5)
    try:
        os.execv(sys.executable, [sys.executable, str(script_path)] + sys.argv[1:])
    except Exception:
        console.print("  [yellow]Could not restart automatically. Please re-run fftoolbox.[/]")
    return True


# ════════════════════════════════════════════════════════════════════════
# UI HELPERS
# ════════════════════════════════════════════════════════════════════════

def print_banner():
    console.print()
    console.print(Panel.fit(
        Align.center(
            f"[bold cyan]{APP_NAME}[/][bold white] Pro[/]  [dim]v{APP_VERSION}[/]  [dim]│[/]  "
            "[italic]Smart Media Converter[/]\n"
            "[dim]Video · Audio Extraction · Audio Conversion · DaVinci Resolve[/]"
        ),
        border_style="cyan", padding=(0,4),
    ))
    console.print()

def print_file_info(info: dict, path: str):
    vs  = video_stream(info)
    dur = file_duration(info)
    sz  = file_size_bytes(info)

    tbl = Table(box=box.ROUNDED, border_style="dim", show_header=False, padding=(0,1))
    tbl.add_column("K", style="bold cyan", width=17); tbl.add_column("V")
    tbl.add_row("File",     escape(Path(path).name))
    tbl.add_row("Size",     human_size(sz))
    tbl.add_row("Duration", human_dur(dur))

    if vs:
        vc = vs.get("codec_name","?").upper()
        w  = vs.get("width","?"); h = vs.get("height","?")
        tbl.add_row("Resolution", f"{w} × {h}")
        tbl.add_row("FPS",        fps_str(vs))
        bit = vs.get("bit_rate")
        if bit: tbl.add_row("Video bitrate", f"{int(bit)//1000} kb/s")
        vc_disp = (f"[bold yellow]⚠ {vc} (professional — large file)[/]"
                   if any(p in vc.lower() for p in PROFESSIONAL_CODECS) else vc)
        tbl.add_row("Video codec", vc_disp)

    for i, as_ in enumerate(all_audio_streams(info)):
        ac = as_.get("codec_name","?").upper()
        sr = as_.get("sample_rate","?")
        ch = as_.get("channels","?")
        ab = as_.get("bit_rate")
        detail = f"{ac}  {sr}Hz  {ch}ch"
        if ab: detail += f"  {int(ab)//1000}kb/s"
        tbl.add_row(f"Audio {i+1}" if len(all_audio_streams(info))>1 else "Audio", detail)

    subs = subtitle_streams(info)
    if subs:
        tbl.add_row("Subtitles", f"{len(subs)} track(s)")

    # Smart tips
    if sz > 500*1024*1024:
        tbl.add_row("[yellow]Tip[/]","[yellow]Large file — [bold]Resolve Cleanup[/] or [bold]Smart[/] suggested[/]")
    if vs and safe_int(vs.get("width")) >= 3840:
        tbl.add_row("[dim]Tip[/]","[dim]4K source detected[/]")
    if is_audio_only(info):
        tbl.add_row("[cyan]Type[/]","[cyan]Audio-only file[/]")

    title = "[bold]Source File[/]" if not is_audio_only(info) else "[bold]Source Audio[/]"
    console.print(Panel(tbl, title=title, border_style="cyan", padding=(0,1)))

def show_presets_table(suggested_key: Optional[str] = None):
    tbl = Table(box=box.SIMPLE_HEAD, border_style="dim", padding=(0,1))
    tbl.add_column("#",      style="bold dim", width=3)
    tbl.add_column("Preset", width=44)
    tbl.add_column("Description")
    last_group = None
    for i, (key, p) in enumerate(PRESETS.items(), 1):
        g = p.get("group","")
        if g != last_group:
            tbl.add_row("", f"[bold dim]{g}[/]", ""); last_group = g
        m = "  [bold cyan]← suggested[/]" if key == suggested_key else ""
        tbl.add_row(str(i),
                    f"[{p['color']}]{p['emoji']}  {p['name']}[/]{m}",
                    f"[dim]{p['desc']}[/]")
    tbl.add_row("i", "[dim]Import saved preset[/]", "")
    console.print(Panel(tbl, title="[bold]Video Presets[/]", border_style="cyan"))

def suggest_preset(info: dict) -> str:
    if is_audio_only(info): return "fix_audio"
    sz = file_size_bytes(info)
    vs = video_stream(info)
    w  = safe_int((vs or {}).get("width"))
    if is_professional(info) or sz > 500*1024*1024: return "resolve_cleanup"
    if w >= 3840: return "smart"
    return "web_1080p"

def _unique_path(path: str) -> str:
    """Return path unchanged if it doesn't exist, else append _1, _2, ..."""
    if not os.path.exists(path): return path
    p   = Path(path)
    for i in range(1, 10000):
        candidate = str(p.parent / f"{p.stem}_{i}{p.suffix}")
        if not os.path.exists(candidate): return candidate
    return str(p.parent / f"{p.stem}_{int(time.time())}{p.suffix}")

# ════════════════════════════════════════════════════════════════════════
# COLLISION HANDLER
# ════════════════════════════════════════════════════════════════════════

def handle_collision(out_path: str) -> Optional[str]:
    console.print(f"\n  [yellow]⚠  Already exists:[/] [dim]{escape(Path(out_path).name)}[/]")
    console.print("  [cyan]1[/]  Overwrite")
    console.print("  [cyan]2[/]  Auto-rename  (_1, _2, …)")
    console.print("  [cyan]3[/]  Enter new name")
    console.print("  [cyan]4[/]  Skip this file")
    c = Prompt.ask("  Choice", choices=["1","2","3","4"], default="2")
    if c == "1": return out_path
    if c == "2": return _unique_path(out_path)
    if c == "3":
        raw = Prompt.ask("  New filename (no extension)").strip()
        if not raw: return None
        new = str(Path(out_path).parent / f"{raw}.mp4")
        if os.path.exists(new): return _unique_path(new)
        return new
    return None  # skip

# ════════════════════════════════════════════════════════════════════════
# FILE BROWSER  (numbers + direct paths + search + recent)
# ════════════════════════════════════════════════════════════════════════

def file_browser(start: str = "~", history: Optional[Dict] = None,
                 audio_mode: bool = False) -> Optional[List[str]]:
    """
    Interactive file browser.
    - Numbers to navigate
    - Paste full/partial path directly
    - Partial name search
    - 'r' = recent files/dirs
    - 'a' = select all media in current dir
    - 'R' = recursive
    """
    extensions = ALL_MEDIA if audio_mode else VIDEO_EXTENSIONS | AUDIO_EXTENSIONS
    current = Path(os.path.expanduser(start)).resolve()

    # If start dir already has videos, we stay there
    while True:
        console.print()
        console.print(Rule(f"[bold cyan]📁  Browser[/]  [dim]{escape(str(current))}[/]"))

        try:
            raw = sorted(current.iterdir(), key=lambda p:(p.is_file(), p.name.lower()))
        except PermissionError:
            console.print("[red]  Permission denied[/]"); current = current.parent; continue

        dirs   = [e for e in raw if e.is_dir()  and not e.name.startswith(".")]
        media  = [e for e in raw if e.is_file() and e.suffix.lower() in extensions]
        items: List[Tuple[Path, bool]] = []

        tbl = Table(box=box.SIMPLE, show_header=True, padding=(0,1))
        tbl.add_column("#",    style="bold dim", width=4)
        tbl.add_column("Name", width=46)
        tbl.add_column("Size", style="dim", width=10)
        tbl.add_column("Info", style="dim", width=12)

        tbl.add_row("0","[bold]↑  .. (go up)[/]","","")
        items.append((current.parent, True))

        for d in dirs[:40]:
            n = len(items)
            try:
                cnt = sum(1 for x in d.iterdir()
                          if x.is_file() and x.suffix.lower() in extensions)
                info_s = f"{cnt} file{'s' if cnt!=1 else ''}" if cnt else ""
            except: info_s = ""
            tbl.add_row(str(n), f"[yellow]📁  {escape(d.name)}[/]", "", info_s)
            items.append((d, True))

        if not media:
            tbl.add_row("", "[dim]  — no media files here —[/]","","")
        for f in media:
            n = len(items)
            ext_tag = f.suffix.upper().lstrip(".")
            color = "green" if f.suffix.lower() in VIDEO_EXTENSIONS else "bright_blue"
            tbl.add_row(str(n), f"[{color}]{'🎬' if f.suffix.lower() in VIDEO_EXTENSIONS else '🎵'}  {escape(f.name)}[/]",
                        human_size(f.stat().st_size), ext_tag)
            items.append((f, False))

        console.print(tbl)
        console.print()

        hints = ["[bold]#[/] navigate/select",
                 "[bold]a[/] all here",
                 "[bold]R[/] recursive",
                 "[bold]r[/] recent",
                 "[bold]/path[/] jump",
                 "[bold]q[/] cancel"]
        console.print("  [dim]" + "  ·  ".join(hints) + "[/]")

        raw_in = Prompt.ask("[bold cyan]  >[/]").strip()
        low    = raw_in.lower()

        if low == "q": return None

        # ── Recent files/dirs ──────────────────────────────────────────
        if low == "r":
            h = history or {}
            rec_dirs  = h.get("recent_dirs",  [])[:8]
            rec_files = h.get("recent_files", [])[:8]
            if not rec_dirs and not rec_files:
                console.print("  [dim]No recent history.[/]"); continue
            tbl2 = Table(box=box.SIMPLE, padding=(0,1), show_header=False)
            tbl2.add_column("#",style="bold dim",width=3); tbl2.add_column("Path"); tbl2.add_column("Type",style="dim")
            recent_items: List[Tuple[str,bool]] = []
            for d in rec_dirs:
                n = len(recent_items)+1
                if Path(d).exists():
                    tbl2.add_row(str(n), f"[yellow]{escape(d)}[/]", "dir")
                    recent_items.append((d, True))
            for f in rec_files:
                n = len(recent_items)+1
                if Path(f).exists():
                    tbl2.add_row(str(n), f"[green]{escape(f)}[/]", "file")
                    recent_items.append((f, False))
            if not recent_items:
                console.print("  [dim]No existing recent paths.[/]"); continue
            console.print(tbl2)
            rc = Prompt.ask("  #", choices=[str(i) for i in range(1,len(recent_items)+1)])
            rpath, ris_dir = recent_items[int(rc)-1]
            if ris_dir: current = Path(rpath).resolve()
            else: return [rpath]
            continue

        # ── All files in dir ───────────────────────────────────────────
        if low == "a":
            if media:
                console.print(f"[green]  ✓  {len(media)} file(s) selected[/]")
                return [str(f) for f in media]
            console.print("[yellow]  No media files here.[/]"); continue

        # ── Recursive ─────────────────────────────────────────────────
        if raw_in.upper() == "R":
            found = [str(f) for f in sorted(current.rglob("*"))
                     if f.is_file() and f.suffix.lower() in extensions]
            if found:
                console.print(f"[green]  ✓  {len(found)} file(s) found recursively[/]")
                return found
            console.print("[yellow]  Nothing found recursively.[/]"); continue

        # ── Direct path input ──────────────────────────────────────────
        if (raw_in.startswith(("/","~","./","../")) or
                (os.sep in raw_in and len(raw_in) > 2)):
            exp = Path(os.path.expanduser(raw_in)).resolve()
            if exp.is_dir():   current = exp; continue
            if exp.is_file():  return [str(exp)]
            # try glob
            matches = list(Path(exp.parent).glob(exp.name)) if exp.parent.exists() else []
            if matches:
                vid = [str(m) for m in matches if m.suffix.lower() in extensions]
                if vid: return sorted(vid)
            console.print(f"  [red]Not found: {escape(raw_in)}[/]"); continue

        # ── Partial name search ────────────────────────────────────────
        if raw_in and not raw_in.isdigit():
            matches = [f for f in media if raw_in.lower() in f.name.lower()]
            if len(matches) == 1: return [str(matches[0])]
            if matches:
                console.print(f"  [yellow]{len(matches)} matches:[/]")
                for m in matches[:6]: console.print(f"  [dim]{m.name}[/]")
            else:
                console.print(f"  [red]No match for '{escape(raw_in)}'[/]")
            continue

        # ── Number ────────────────────────────────────────────────────
        try: idx = int(raw_in)
        except: console.print("[red]  Enter a number or command.[/]"); continue
        if idx < 0 or idx >= len(items):
            console.print(f"[red]  Out of range (0–{len(items)-1}).[/]"); continue
        path, is_dir = items[idx]
        if is_dir: current = path.resolve()
        else:      return [str(path)]

# ════════════════════════════════════════════════════════════════════════
# RESOLUTION PICKER
# ════════════════════════════════════════════════════════════════════════

def pick_resolution(src_w=None, src_h=None,
                    recommended=None, default_res=None) -> Optional[Tuple[int,int]]:
    console.print()
    console.print("[bold cyan]Output Resolution  (never upscales)[/]")
    tbl = Table(box=box.SIMPLE, padding=(0,1), show_header=False)
    tbl.add_column("#", style="bold dim", width=4)
    tbl.add_column("Resolution")
    tbl.add_column("Note", style="dim")
    for i,(w,h,label) in enumerate(RESOLUTIONS):
        notes = []
        if default_res   and (w,h)==default_res:   notes.append("preset default")
        if recommended   and (w,h)==recommended:   notes.append("[bold cyan]← recommended[/]")
        if w and src_w and src_h and (w>src_w or h>src_h): notes.append("(larger than source)")
        tbl.add_row(str(i), label, "  ".join(notes))
    tbl.add_row(str(len(RESOLUTIONS)), "Custom (enter W × H)", "")
    console.print(tbl)
    di = 0
    if recommended:
        for i,(w,h,_) in enumerate(RESOLUTIONS):
            if (w,h)==recommended: di=i; break
    elif default_res:
        for i,(w,h,_) in enumerate(RESOLUTIONS):
            if (w,h)==default_res: di=i; break
    c = Prompt.ask("Choice",
                   choices=[str(i) for i in range(len(RESOLUTIONS)+1)],
                   default=str(di))
    idx = int(c)
    if idx == 0: return None
    if idx < len(RESOLUTIONS):
        w,h,_ = RESOLUTIONS[idx]; return (w,h) if w else None
    w = int(Prompt.ask("  Width (px)")); h = int(Prompt.ask("  Height (px)"))
    return ((w//2)*2,(h//2)*2)

# ════════════════════════════════════════════════════════════════════════
# CUSTOM PRESET BUILDER
# ════════════════════════════════════════════════════════════════════════

def build_custom_preset(info: Optional[dict]) -> dict:
    preset: Dict[str,Any] = {
        "group":"Custom","name":"Custom","emoji":"⚙️","color":"white","tip":"Custom",
        "codec":None,"crf":None,"speed":None,"audio_codec":"aac","audio_kbps":128,
        "max_res":None,"target_mb":None,"two_pass":False,
    }
    console.print()
    console.print(Rule("[bold]⚙️  Custom Configuration[/]"))

    # Codec
    console.print("\n[bold cyan]Video Codec[/]")
    codec_opts = [
        ("libx264","H.264 — widest compatibility"),
        ("libx265","H.265 — ~40% smaller, modern devices"),
        ("copy",   "Copy video unchanged  (recode audio only, instant)"),
        ("libaom-av1","AV1 — next-gen, very slow encode"),
        ("libvpx-vp9","VP9 — open source, good quality"),
    ]
    hw = detect_hw_encoders()
    all_codecs = codec_opts + [(e,f"[HW] {l}") for e,l in hw]
    tbl = Table(box=box.SIMPLE,padding=(0,1),show_header=False)
    tbl.add_column("#",style="bold dim",width=3); tbl.add_column("Option")
    for i,(e,l) in enumerate(all_codecs,1): tbl.add_row(str(i),l)
    console.print(tbl)
    c = Prompt.ask("Codec",choices=[str(i) for i in range(1,len(all_codecs)+1)],default="1")
    preset["codec"] = all_codecs[int(c)-1][0]

    if preset["codec"] != "copy":
        # Quality
        console.print("\n[bold cyan]Quality / Size Control[/]")
        console.print("  [cyan]1[/]  CRF  (constant quality — recommended)")
        console.print("  [cyan]2[/]  Target file size in MB  (two-pass)")
        console.print("  [cyan]3[/]  Target % of original size  (two-pass)")
        qm = Prompt.ask("Mode", choices=["1","2","3"], default="1")
        if qm == "1":
            console.print("  [dim]0=lossless · 15=excellent · 18=high · 23=default · 28=compact · 33=tiny[/]")
            preset["crf"] = int(Prompt.ask("CRF", default="23"))
        elif qm == "2":
            tgt = float(Prompt.ask("Target MB", default="100"))
            preset["target_mb"] = tgt; preset["two_pass"] = True
            console.print(f"  [dim]Safety margin ({BITRATE_SAFETY*100:.0f}%): actual target ≈ {tgt*BITRATE_SAFETY:.0f} MB[/]")
        else:
            pct = float(Prompt.ask("Keep what % (e.g. 30)", default="30"))
            preset["_pct"] = pct/100.0; preset["two_pass"] = True

        # Speed
        HW = {"nvenc","vaapi","qsv","videotoolbox","amf"}
        if not any(h in preset["codec"] for h in HW):
            console.print("\n[bold cyan]Encode Speed[/]")
            speed_map = {"1":"ultrafast","2":"superfast","3":"veryfast","4":"faster",
                         "5":"fast","6":"medium","7":"slow","8":"slower","9":"veryslow"}
            for k,v in speed_map.items(): console.print(f"  [cyan]{k}[/]  {v}")
            sp = Prompt.ask("Speed", choices=list(speed_map.keys()), default="7")
            preset["speed"] = speed_map[sp]

        # Resolution
        vs   = video_stream(info) if info else None
        src_w = safe_int((vs or {}).get("width"))  if vs else None
        src_h = safe_int((vs or {}).get("height")) if vs else None
        rec   = None
        if preset.get("target_mb") and src_w and src_h:
            dur = file_duration(info) if info else 0
            rec, expl = recommend_resolution(preset["target_mb"],dur,
                                             preset.get("audio_kbps",128),src_w,src_h)
            console.print(f"\n  [dim]Recommendation: {expl}[/]")
        preset["max_res"] = pick_resolution(src_w, src_h, recommended=rec)

        # Extra options
        console.print("\n[bold cyan]Extra Options[/]")
        if Confirm.ask("  Deinterlace (interlaced/TV source)?", default=False):
            preset["_deinterlace"] = True
        if Confirm.ask("  Noise reduction (hqdn3d)?", default=False):
            preset["_denoise"] = True
        if info and subtitle_streams(info):
            if Confirm.ask(f"  Copy subtitle tracks ({len(subtitle_streams(info))} found)?", default=True):
                preset["_copy_subs"] = True
        if not preset.get("two_pass"):
            if Confirm.ask("  Force two-pass encoding?", default=False):
                preset["two_pass"] = True
        if Confirm.ask("  Preserve metadata (title, artist, etc.)?", default=True):
            preset["_copy_meta"] = True

    # Audio
    console.print("\n[bold cyan]Audio[/]")
    audio_opts = [
        ("aac",      "AAC — best compatibility (recommended)"),
        ("pcm_s16le","PCM 16-bit — lossless · DaVinci Resolve compatible"),
        ("pcm_s24le","PCM 24-bit — lossless · studio quality"),
        ("libopus",  "Opus — efficient, modern"),
        ("libmp3lame","MP3 — universal"),
        ("flac",     "FLAC — lossless compressed"),
        ("copy",     "Copy audio unchanged"),
        ("__none__", "Remove all audio (silent video)"),
    ]
    tbl2 = Table(box=box.SIMPLE,padding=(0,1),show_header=False)
    tbl2.add_column("#",style="bold dim",width=3); tbl2.add_column("Option")
    for i,(e,l) in enumerate(audio_opts,1): tbl2.add_row(str(i),l)
    console.print(tbl2)
    ac = Prompt.ask("Audio", choices=[str(i) for i in range(1,len(audio_opts)+1)], default="1")
    preset["audio_codec"] = audio_opts[int(ac)-1][0]
    if preset["audio_codec"] == "__none__":
        preset["audio_codec"] = None; preset["_no_audio"] = True
    elif preset["audio_codec"] not in ("copy","flac","pcm_s16le","pcm_s24le"):
        preset["audio_kbps"] = int(Prompt.ask("Audio kb/s", default="192"))

    if info and len(all_audio_streams(info)) > 1:
        console.print(f"\n  [yellow]⚠  {len(all_audio_streams(info))} audio tracks found.[/]")
        if Confirm.ask("  Include ALL audio tracks?", default=True):
            preset["_all_audio"] = True

    # Save option
    if Confirm.ask("\n  Save this preset for future use?", default=False):
        n = Prompt.ask("  Preset name").strip()
        if n: export_preset(preset, n)

    return preset

# ════════════════════════════════════════════════════════════════════════
# CONFIGURE PRESET (interactive per-preset questions)
# ════════════════════════════════════════════════════════════════════════

def configure_preset(key: str, preset: dict, info: Optional[dict]) -> dict:
    preset = deepcopy(preset)

    if key == "smart":
        if info:
            console.print("\n  [dim]Analyzing video …[/]")
            preset = compute_smart_preset(info)
        else:
            preset["crf"] = 23; preset["speed"] = "slow"

    elif key == "resolve_audio_fix":
        vs = video_stream(info) if info else None
        if vs:
            vc = vs.get("codec_name","?")
            console.print(f"\n  [dim]Video codec: {vc.upper()} → will be copied unchanged[/]")
        console.print(
            "\n  [dim]DaVinci Resolve on Linux often rejects AAC, Opus, and MP3 audio.\n"
            "  This preset converts audio to [bold]PCM 16-bit 48 kHz[/] in a .mov container\n"
            "  — the format Resolve handles most reliably.[/]"
        )
        bit_depth = Prompt.ask("  PCM bit depth", choices=["16","24","32"], default="16")
        preset["audio_codec"] = f"pcm_s{bit_depth}le"

    elif key == "resolve_import_ready":
        console.print(
            "\n  [dim]This encodes video to H.264 and audio to PCM in a .mov container.\n"
            "  Use this to make any video ready for DaVinci Resolve on Linux.[/]"
        )
        if info:
            vs  = video_stream(info)
            src_w = safe_int((vs or {}).get("width")) if vs else None
            src_h = safe_int((vs or {}).get("height")) if vs else None
            if Confirm.ask("  Change resolution?", default=False):
                preset["max_res"] = pick_resolution(src_w, src_h)

    elif key == "target_mb":
        console.print()
        console.print(Panel(
            f"[dim]Two-pass with [bold]{BITRATE_SAFETY*100:.0f}%[/] safety margin.\n"
            "Output is always UNDER your target (rare edge-cases auto-retry at 90%).\n"
            "WhatsApp: [bold]100 MB[/]  ·  Telegram: [bold]2 GB[/]  ·  Email: [bold]25 MB[/][/]",
            border_style="dim",title="[dim]Target Size Info[/]",
        ))
        tgt = float(Prompt.ask("Target MB", default="100"))
        preset["target_mb"] = tgt
        console.print(f"  [dim]Internal target: {tgt*BITRATE_SAFETY:.1f} MB ({BITRATE_SAFETY*100:.0f}% safety)[/]")
        vs    = video_stream(info) if info else None
        src_w = safe_int((vs or {}).get("width",1920))  if vs else 1920
        src_h = safe_int((vs or {}).get("height",1080)) if vs else 1080
        dur   = file_duration(info) if info else 0
        rec, expl = recommend_resolution(tgt, dur, preset.get("audio_kbps",128), src_w, src_h)
        console.print(f"  [dim]{expl}[/]")
        preset["max_res"] = pick_resolution(src_w, src_h, recommended=rec)

    elif key == "target_percent":
        sz = file_size_bytes(info) if info else 0
        console.print()
        if sz > 0:
            console.print(f"  [dim]Source: {sz/1024/1024:.1f} MB[/]")
            console.print("  [dim]10 = tiny  ·  30 = aggressively smaller  ·  50 = half  ·  80 = subtle[/]")
        pct = float(Prompt.ask("Keep what % of original?", default="30"))
        preset["_pct"] = pct/100.0
        if sz > 0:
            est_tgt = sz/1024/1024 * pct/100.0
            vs    = video_stream(info) if info else None
            src_w = safe_int((vs or {}).get("width",1920))  if vs else 1920
            src_h = safe_int((vs or {}).get("height",1080)) if vs else 1080
            dur   = file_duration(info) if info else 0
            rec, expl = recommend_resolution(est_tgt, dur, preset.get("audio_kbps",128), src_w, src_h)
            console.print(f"  [dim]{expl}[/]")
            preset["max_res"] = pick_resolution(src_w, src_h, recommended=rec)

    elif key == "whatsapp":
        console.print(
            "\n  [dim]WhatsApp video (with preview): [bold]100 MB[/] · 720p\n"
            "  As document (no preview): up to [bold]2 GB[/][/]"
        )
        as_doc = Confirm.ask("  Send as document?", default=False)
        if as_doc:
            preset["target_mb"] = None; preset["max_res"] = None
            preset["crf"] = 20; preset["two_pass"] = False
        else:
            tgt = float(Prompt.ask("  Target MB", default="95"))
            preset["target_mb"] = tgt
            console.print(f"  [dim]Safety margin: internal target {tgt*BITRATE_SAFETY:.0f} MB[/]")

    elif key in ("compress_light","compress_medium","compress_heavy"):
        console.print()
        if Confirm.ask("  Override output resolution?", default=False):
            preset["max_res"] = pick_resolution(default_res=preset.get("max_res"))

    elif key == "custom":
        preset = build_custom_preset(info)

    return preset

# ════════════════════════════════════════════════════════════════════════
# COMMAND BUILDER
# ════════════════════════════════════════════════════════════════════════

def build_vf_list(preset: dict, src_w, src_h) -> List[str]:
    f = []
    if preset.get("_deinterlace"): f.append("yadif=mode=1")
    if preset.get("_denoise"):     f.append("hqdn3d=4:3:6:4.5")
    mr = preset.get("max_res")
    if mr and src_w and src_h:
        sf = scale_vf(src_w, src_h, mr)
        if sf: f.append(sf)
    if not any("scale=" in x for x in f):
        f.append("scale=trunc(iw/2)*2:trunc(ih/2)*2")
    return f

def build_cmd(input_path: str, output_path: str, preset: dict,
              src_w, src_h, video_kbps=None,
              pass_num: int = 0, passlog: Optional[str] = None) -> List[str]:

    out_ext = preset.get("_output_ext", ".mp4")
    # Override extension in output_path if needed
    if not output_path.endswith(out_ext):
        output_path = str(Path(output_path).with_suffix(out_ext))

    cmd = ["ffmpeg","-hide_banner","-y","-i",input_path]
    co  = preset.get("codec") or "libx264"
    HW  = {"nvenc","vaapi","qsv","videotoolbox","amf"}

    # Metadata preservation
    if preset.get("_copy_meta"): cmd += ["-map_metadata","0"]

    # ── Copy-video path ────────────────────────────────────────────────
    if co == "copy":
        if preset.get("_no_audio"):
            cmd += ["-map","0:v","-c:v","copy","-an"]
        elif preset.get("_all_audio"):
            cmd += ["-map","0:v","-map","0:a","-c:v","copy"]
        else:
            cmd += ["-map","0:v","-map","0:a?","-c:v","copy"]

        if preset.get("_copy_subs"):
            cmd += ["-map","0:s?","-c:s","copy"]

        if not preset.get("_no_audio"):
            ac = preset.get("audio_codec") or "aac"
            ab = preset.get("audio_kbps")
            if ac in ("copy","flac","pcm_s16le","pcm_s24le","pcm_s32le"):
                cmd += ["-c:a", ac]
                if "pcm" in ac: cmd += ["-ar","48000"]
            else:
                cmd += ["-c:a", ac]
                if ab: cmd += ["-b:a", f"{ab}k"]
                cmd += ["-ar","48000"]

        if out_ext == ".mp4": cmd += ["-movflags","+faststart"]
        cmd += [output_path]; return cmd

    # ── Video filters ─────────────────────────────────────────────────
    vf = build_vf_list(preset, src_w, src_h)
    if vf: cmd += ["-vf",",".join(vf)]

    # Stream mapping
    if preset.get("_no_audio"):
        cmd += ["-map","0:v","-an"]
    elif preset.get("_all_audio"):
        cmd += ["-map","0:v","-map","0:a"]
    else:
        cmd += ["-map","0:v","-map","0:a?"]
    if preset.get("_copy_subs"):
        cmd += ["-map","0:s?","-c:s","copy"]

    # Video codec
    if co == "libx264":
        cmd += ["-c:v","libx264","-profile:v","high","-pix_fmt","yuv420p"]
    elif co == "libx265":
        cmd += ["-c:v","libx265","-pix_fmt","yuv420p","-tag:v","hvc1"]
    else:
        cmd += ["-c:v",co,"-pix_fmt","yuv420p"]

    # Bitrate / CRF
    if video_kbps:
        mr = int(video_kbps*1.3); bs = int(video_kbps*2.0)
        cmd += ["-b:v",f"{video_kbps}k","-maxrate",f"{mr}k","-bufsize",f"{bs}k"]
    elif preset.get("crf") is not None:
        cmd += ["-crf",str(preset["crf"])]

    # Speed preset
    sp = preset.get("speed")
    if sp and not any(h in co for h in HW): cmd += ["-preset",sp]

    # Two-pass
    if pass_num == 1:
        cmd += ["-pass","1","-passlogfile",passlog,"-an","-f","mp4","/dev/null"]
        return cmd
    elif pass_num == 2:
        cmd += ["-pass","2","-passlogfile",passlog]

    # Audio
    if not preset.get("_no_audio"):
        ac = preset.get("audio_codec") or "aac"
        ab = preset.get("audio_kbps")
        if ac in ("copy","flac","pcm_s16le","pcm_s24le","pcm_s32le"):
            cmd += ["-c:a", ac]
            if "pcm" in ac: cmd += ["-ar","48000"]
        else:
            cmd += ["-c:a", ac]
            if ab: cmd += ["-b:a", f"{ab}k"]
            cmd += ["-ar","48000"]

    if out_ext == ".mp4": cmd += ["-movflags","+faststart"]
    cmd += [output_path]; return cmd

# ════════════════════════════════════════════════════════════════════════
# PROGRESS
# ════════════════════════════════════════════════════════════════════════

def run_with_progress(cmd: List[str], duration_s: float, label: str = "Encoding") -> bool:
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description:<26}"),
        BarColumn(bar_width=34,complete_style="cyan",finished_style="green"),
        TaskProgressColumn(),
        TextColumn("[dim]{task.fields[eta]:<14}"),
        TextColumn("[dim]{task.fields[speed]}"),
        console=console,transient=False,
    ) as prog:
        task = prog.add_task(label, total=100, eta="", speed="")
        try:
            proc = subprocess.Popen(cmd, stderr=subprocess.PIPE,
                                    stdout=subprocess.DEVNULL, text=True)
        except FileNotFoundError:
            console.print("[red]  ffmpeg not found![/]"); return False

        for line in proc.stderr:
            t = parse_progress_time(line)
            if t and duration_s > 0:
                pct  = min(99.9, t/duration_s*100)
                sm   = re.search(r"speed=\s*([\d.]+)x", line)
                spd  = float(sm.group(1)) if sm else 0.0
                sp_s = f"{spd:.1f}×" if spd>0 else ""
                rem  = (duration_s-t)/spd if spd>0.01 else 0
                eta  = f"ETA {human_dur(rem)}" if rem > 2 else ""
                prog.update(task, completed=pct, speed=sp_s, eta=eta)

        proc.wait()
        if proc.returncode == 0:
            prog.update(task, completed=100, eta="", speed="done ✓")
            return True
        prog.stop()
        console.print(f"[red]  ✗  FFmpeg exited {proc.returncode}[/]")
        return False

# ════════════════════════════════════════════════════════════════════════
# ENCODE FILE (HW fallback + post-encode size verification)
# ════════════════════════════════════════════════════════════════════════

def encode_file(input_path: str, output_path: str, preset: dict,
                info: dict, idx: int = 0, total: int = 1) -> Tuple[bool, str]:
    """Returns (success, actual_output_path)."""
    duration = file_duration(info)
    vs       = video_stream(info)
    src_w    = safe_int((vs or {}).get("width"))  if vs else None
    src_h    = safe_int((vs or {}).get("height")) if vs else None
    label_p  = f"[{idx}/{total}] " if total > 1 else ""

    # Fix output extension for Resolve presets
    out_ext = preset.get("_output_ext", ".mp4")
    if not output_path.endswith(out_ext):
        output_path = str(Path(output_path).with_suffix(out_ext))

    # HW encoder fallback
    co = preset.get("codec") or "libx264"
    HW = {"nvenc","vaapi","qsv","videotoolbox","amf"}
    if any(h in co for h in HW):
        preset = deepcopy(preset)
        preset["codec"] = hw_fallback(co, input_path)

    # Percent target
    if preset.get("_pct") and file_size_bytes(info) > 0 and duration > 0:
        preset = deepcopy(preset)
        preset["target_mb"] = file_size_bytes(info)/1024/1024 * preset["_pct"]
        console.print(f"  [dim]Target: {preset['target_mb']:.1f} MB ({preset['_pct']*100:.0f}% of original)[/]")

    # Copy path
    if preset.get("codec") == "copy":
        cmd = build_cmd(input_path, output_path, preset, src_w, src_h)
        output_path = cmd[-1]  # might have been updated with new ext
        ok = run_with_progress(cmd, duration, f"{label_p}Remuxing")
        return ok, output_path

    # Two-pass
    if preset.get("target_mb") and duration > 0:
        akbps   = preset.get("audio_kbps") or 128
        vkbps   = target_video_kbps(preset["target_mb"], duration, akbps, BITRATE_SAFETY)
        tmpdir  = tempfile.mkdtemp(prefix="fftoolbox_")
        passlog = os.path.join(tmpdir,"ff2pass")
        est_mb  = (vkbps+akbps)*1000*duration/(8*1024*1024)

        safe_tgt = preset["target_mb"] * BITRATE_SAFETY
        console.print(
            f"  [dim]Two-pass  ·  user target [bold]{preset['target_mb']:.0f} MB[/]  ·  "
            f"safety target [bold]{safe_tgt:.0f} MB[/]  ·  "
            f"video {vkbps} kb/s  ·  est. [bold]{est_mb:.1f} MB[/][/]"
        )

        cmd1 = build_cmd(input_path, output_path, preset, src_w, src_h, vkbps, 1, passlog)
        ok = run_with_progress(cmd1, duration, f"{label_p}Pass 1/2")
        if ok:
            cmd2 = build_cmd(input_path, output_path, preset, src_w, src_h, vkbps, 2, passlog)
            output_path = cmd2[-1]
            ok = run_with_progress(cmd2, duration, f"{label_p}Pass 2/2")
        try: shutil.rmtree(tmpdir)
        except: pass

        # Post-encode verification — retry if over budget
        if ok and os.path.exists(output_path):
            actual_mb = os.path.getsize(output_path)/1024/1024
            user_tgt  = preset["target_mb"]
            if actual_mb > user_tgt:
                over = actual_mb - user_tgt
                console.print(
                    f"  [yellow]⚠  Output {actual_mb:.1f} MB — {over:.1f} MB over target. "
                    f"Auto-retrying at 90% margin …[/]"
                )
                vkbps2   = target_video_kbps(user_tgt, duration, akbps, 0.90)
                tmpdir2  = tempfile.mkdtemp(prefix="fftoolbox_retry_")
                passlog2 = os.path.join(tmpdir2,"ff2pass")
                c1 = build_cmd(input_path, output_path, preset, src_w, src_h, vkbps2, 1, passlog2)
                r1 = run_with_progress(c1, duration, f"{label_p}Retry 1/2")
                if r1:
                    c2 = build_cmd(input_path, output_path, preset, src_w, src_h, vkbps2, 2, passlog2)
                    output_path = c2[-1]
                    run_with_progress(c2, duration, f"{label_p}Retry 2/2")
                try: shutil.rmtree(tmpdir2)
                except: pass

        return ok, output_path

    # Single-pass CRF
    cmd = build_cmd(input_path, output_path, preset, src_w, src_h)
    output_path = cmd[-1]
    ok = run_with_progress(cmd, duration, f"{label_p}Encoding")
    return ok, output_path

# ════════════════════════════════════════════════════════════════════════
# OUTPUT DIR PICKER
# ════════════════════════════════════════════════════════════════════════

class OutputConfig:
    """Encapsulates where and how outputs are written."""
    mode:          str  = "subfolder"   # subfolder | same | desktop | custom | inplace | inplace_backup
    base_dir:      str  = ""            # absolute output root (unused for inplace modes)
    batch_root:    Optional[str] = None # root of recursive batch; None = flat output
    backup_suffix: str  = "_originals"  # folder name for backed-up originals

    def output_path_for(self, src_path: str, sfx: str, ext: str) -> str:
        """
        Compute the output file path for src_path.

        - inplace:        overwrite src in-place (no backup)
        - inplace_backup: move original to <parent>/_originals/, write new to original location
        - otherwise:      write to base_dir, preserving subdir structure if batch_root is set
        """
        src = Path(src_path)

        if self.mode in ("inplace", "inplace_backup"):
            return str(src.with_suffix(ext))

        # Preserve subfolder structure when batch_root is known
        if self.batch_root:
            try:
                rel = src.parent.relative_to(self.batch_root)
                out_parent = Path(self.base_dir) / rel
            except ValueError:
                out_parent = Path(self.base_dir)
        else:
            out_parent = Path(self.base_dir)

        out_parent.mkdir(parents=True, exist_ok=True)
        return str(out_parent / f"{src.stem}_{sfx}{ext}")

    def prepare_inplace_backup(self, src_path: str) -> Optional[str]:
        """
        For inplace_backup mode: move original to _originals/ subfolder.
        Returns the backup path, or None on failure.
        """
        if self.mode != "inplace_backup":
            return None
        src     = Path(src_path)
        bak_dir = src.parent / self.backup_suffix
        bak_dir.mkdir(exist_ok=True)
        bak_path = _unique_path(str(bak_dir / src.name))
        try:
            shutil.move(str(src), bak_path)
            return bak_path
        except Exception as e:
            console.print(f"  [red]  Could not backup original: {e}[/]")
            return None


def pick_output_mode(files: List[str], history: Optional[Dict] = None) -> OutputConfig:
    """
    Ask user how/where to write outputs.
    Returns an OutputConfig describing the chosen strategy.
    """
    cfg = OutputConfig()

    # Detect batch root (common ancestor of all files)
    if len(files) > 1:
        parents = [Path(f).parent for f in files]
        try:
            common = Path(os.path.commonpath([str(p) for p in parents]))
        except ValueError:
            common = parents[0]
        cfg.batch_root = str(common)
    else:
        cfg.batch_root = None

    first   = files[0]
    src_dir = Path(first).parent
    beside  = str(src_dir / "fftoolbox_output")
    desktop = os.path.expanduser("~/Desktop/fftoolbox_output")
    last    = (history or {}).get("last_output_dir")

    # Build batch root label
    root_label = ""
    if cfg.batch_root and len(files) > 1:
        root_label = f"  [dim](subfolder structure preserved under {escape(cfg.batch_root)})[/]"

    console.print()
    console.print("[bold cyan]Output Mode[/]")
    console.print(f"  [cyan]1[/]  Subfolder beside source [dim]{escape(beside)}[/]{root_label}")
    console.print(f"  [cyan]2[/]  Desktop                 [dim]{escape(desktop)}[/]")
    console.print()
    console.print("  [cyan]3[/]  [bold]In-place — replace originals[/]  [dim](originals moved to _originals/ first)[/]")
    console.print("  [cyan]4[/]  [bold]In-place — overwrite[/]          [dim](no backup, careful!)[/]")
    console.print()
    if last and last not in (beside, desktop):
        console.print(f"  [cyan]5[/]  Last used  [dim]{escape(last)}[/]")
        console.print("  [cyan]6[/]  Custom path")
        choices = ["1","2","3","4","5","6"]
    else:
        console.print("  [cyan]5[/]  Custom path")
        choices = ["1","2","3","4","5"]

    c = Prompt.ask("Choice", choices=choices, default="1")

    if c == "1":
        cfg.mode     = "subfolder"
        cfg.base_dir = beside
    elif c == "2":
        cfg.mode     = "subfolder"
        cfg.base_dir = desktop
    elif c == "3":
        cfg.mode = "inplace_backup"
        backup_name = Prompt.ask(
            "  Backup folder name", default="_originals"
        ).strip() or "_originals"
        cfg.backup_suffix = backup_name
        console.print(
            f"  [dim]Originals → [bold]<source_dir>/{backup_name}/[/] · "
            "converted files replace them in the original location[/]"
        )
        return cfg
    elif c == "4":
        if not Confirm.ask(
            "  [bold red]Overwrite originals with no backup?[/]", default=False
        ):
            console.print("  [dim]Switched to in-place with backup.[/]")
            cfg.mode = "inplace_backup"
        else:
            cfg.mode = "inplace"
        return cfg
    elif c == "5" and last and last not in (beside, desktop):
        cfg.mode     = "subfolder"
        cfg.base_dir = last
    else:
        cfg.mode     = "subfolder"
        cfg.base_dir = os.path.expanduser(Prompt.ask("Path").strip())

    os.makedirs(cfg.base_dir, exist_ok=True)
    return cfg

# ════════════════════════════════════════════════════════════════════════
# SIZE FEEDBACK
# ════════════════════════════════════════════════════════════════════════

def size_feedback(src_sz: int, dst_path: str, preset_key: str) -> None:
    try: dst_sz = os.path.getsize(dst_path)
    except: return
    pct = (1 - dst_sz/src_sz)*100 if src_sz > 0 else 0
    clr = "green" if pct > 5 else ("yellow" if pct > -5 else "red")
    direction = "smaller" if pct > 0 else "LARGER"
    console.print(
        f"  [green]✓[/]  {human_size(src_sz)} → [{clr}]{human_size(dst_sz)}[/]"
        f"  ({abs(pct):.1f}% {direction})"
    )
    dst_mb = dst_sz / 1024 / 1024
    if preset_key == "whatsapp" and dst_mb > WHATSAPP_MB:
        console.print(
            f"\n  [bold yellow]⚠  {dst_mb:.1f} MB > WhatsApp {WHATSAPP_MB} MB limit.[/]\n"
            "  [dim]Use [bold]Target File Size[/] at 95 MB, or send as document (up to 2 GB, no preview).[/]"
        )
    elif dst_sz > src_sz and dst_sz-src_sz > 512*1024:
        console.print("  [yellow]⚠  Output larger than input — source already well-compressed.[/]")

# ════════════════════════════════════════════════════════════════════════
# DETECT VIDEOS IN CWD
# ════════════════════════════════════════════════════════════════════════

def detect_cwd_media() -> Tuple[List[str], List[str]]:
    """Returns (video_files, audio_files) in current working directory."""
    cwd = Path.cwd()
    vids = sorted(str(f) for f in cwd.iterdir()
                  if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS)
    auds = sorted(str(f) for f in cwd.iterdir()
                  if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS)
    return vids, auds

# ════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════

def main():
    # Background update check
    _start_update_check()

    print_banner()
    show_update_banner()

    # Dependency check
    have_ffmpeg, have_ffprobe = check_deps()
    if not have_ffmpeg or not have_ffprobe:
        missing = (["ffmpeg"] if not have_ffmpeg else []) + (["ffprobe"] if not have_ffprobe else [])
        console.print(Panel(
            f"[bold red]Missing:[/] {', '.join(missing)}\n\n"
            "[dim]Ubuntu/Debian:  sudo apt install ffmpeg\n"
            "Arch:           sudo pacman -S ffmpeg\n"
            "macOS:          brew install ffmpeg[/]",
            border_style="red",title="[red]Dependency Error[/]",
        ))
        sys.exit(1)

    hw = detect_hw_encoders()
    if hw:
        console.print("  [dim]⚡ Hardware: " + ", ".join(l for _,l in hw[:3])
                      + ("[/]" if len(hw)<=3 else f" +{len(hw)-3} more[/]"))
        console.print()

    history = load_history()

    # ════════════════════════════════════════════════════════════════════
    # MAIN MENU — choose mode
    # ════════════════════════════════════════════════════════════════════
    cwd_vids, cwd_auds = detect_cwd_media()
    cwd_media = cwd_vids + cwd_auds

    console.print(Rule("[bold]What do you want to do?[/]"))
    console.print()
    console.print("  [cyan]1[/]  Convert video files  [dim](re-encode, compress, share)[/]")
    console.print("  [cyan]2[/]  Extract audio from video  [dim](video → MP3/AAC/FLAC/…)[/]")
    console.print("  [cyan]3[/]  Convert audio files  [dim](MP3 → FLAC, AAC → Opus, …)[/]")
    console.print("  [cyan]4[/]  Fix for DaVinci Resolve Linux  [dim](audio codec fix, quick)[/]")
    console.print("  [cyan]u[/]  Check for updates  [dim](github.com/oskar26/FFToolbox)[/]")

    if cwd_media:
        console.print()
        console.print(
            f"  [dim]📁 Found [bold]{len(cwd_media)}[/] media file(s) in current directory — "
            f"use [bold]c[/] to select all[/]"
        )

    console.print()
    mode_choices = ["1","2","3","4","u"]
    if cwd_media: mode_choices.append("c")
    mode = Prompt.ask("Mode", choices=mode_choices, default="1")

    # Update trigger from within the app
    if mode == "u":
        # Give background thread a moment to finish if it hasn't
        time.sleep(0.3)
        if not _update_info.available:
            # Fetch synchronously since user explicitly asked
            with console.status("[cyan]Checking GitHub for updates …[/]"):
                _fetch_update_info()
        if _update_info.available:
            perform_update(interactive=True)
        else:
            console.print(f"\n  [green]✓  You are on the latest version (v{APP_VERSION}).[/]")
        return

    # Quick shortcut: use CWD files
    if mode == "c":
        mode = Prompt.ask(
            "  Convert as [bold]video[/] (1), extract [bold]audio[/] (2), "
            "[bold]Resolve fix[/] (4)?",
            choices=["1","2","4"], default="1"
        )
        files_override = cwd_media
    else:
        files_override = None

    # ════════════════════════════════════════════════════════════════════
    # STEP 1 — File selection
    # ════════════════════════════════════════════════════════════════════
    console.print()
    console.print(Rule("[bold]Step 1 · Select File(s)[/]"))
    console.print()

    if files_override:
        files = files_override
        console.print(f"  [green]✓[/]  Using [bold]{len(files)}[/] file(s) from current directory")
        for f in files[:4]: console.print(f"  [dim]{escape(Path(f).name)}[/]")
        if len(files)>4: console.print(f"  [dim]… and {len(files)-4} more[/]")
    else:
        audio_only_mode = (mode in ("2","3"))
        console.print("  [cyan]1[/]  Browse interactively")
        console.print("  [cyan]2[/]  Paste file or directory path")
        console.print("  [cyan]3[/]  Entire folder  [dim](batch)[/]")

        if history.get("recent_dirs"):
            console.print(f"  [cyan]4[/]  Recent: [dim]{escape(history['recent_dirs'][0])}[/]")
            sel_choices = ["1","2","3","4"]
        else:
            sel_choices = ["1","2","3"]

        sel = Prompt.ask("How", choices=sel_choices, default="1")
        files: List[str] = []

        if sel == "1":
            start = (history.get("recent_dirs") or [os.path.expanduser("~")])[0]
            result = file_browser(start, history=history, audio_mode=audio_only_mode)
            if not result: console.print("[yellow]  Cancelled.[/]"); return
            files = result
        elif sel == "2":
            raw = os.path.expanduser(Prompt.ask("Path").strip())
            p   = Path(raw)
            ext = ALL_MEDIA if audio_only_mode else (VIDEO_EXTENSIONS | AUDIO_EXTENSIONS)
            if p.is_file():
                files = [str(p)]
            elif p.is_dir():
                files = sorted(str(f) for f in p.iterdir()
                               if f.is_file() and f.suffix.lower() in ext)
            else:
                console.print(f"[red]  Not found: {raw}[/]"); return
        elif sel == "3":
            raw = os.path.expanduser(Prompt.ask("Directory path").strip())
            p   = Path(raw)
            if not p.is_dir(): console.print("[red]  Not a directory.[/]"); return
            recursive = Confirm.ask("  Include subdirectories?", default=False)
            ext = ALL_MEDIA if audio_only_mode else (VIDEO_EXTENSIONS | AUDIO_EXTENSIONS)
            g   = p.rglob("*") if recursive else p.iterdir()
            files = sorted(str(f) for f in g if f.is_file() and f.suffix.lower() in ext)
        elif sel == "4" and history.get("recent_dirs"):
            d = history["recent_dirs"][0]
            ext = ALL_MEDIA if audio_only_mode else (VIDEO_EXTENSIONS | AUDIO_EXTENSIONS)
            files = sorted(str(f) for f in Path(d).iterdir()
                          if f.is_file() and f.suffix.lower() in ext)
            console.print(f"  [dim]{len(files)} file(s) from {escape(d)}[/]")

    if not files: console.print("[red]  No files found.[/]"); return
    files = sorted(set(files))
    console.print(f"\n  [green]✓[/]  [bold]{len(files)} file(s) selected[/]")
    for f in files[:4]: console.print(f"  [dim]{escape(f)}[/]")
    if len(files)>4: console.print(f"  [dim]… +{len(files)-4} more[/]")

    # Probe first file
    console.print()
    first_info = run_ffprobe(files[0])
    if first_info: print_file_info(first_info, files[0])
    else: console.print("[yellow]  Could not read media info.[/]")

    infos: Dict[str, Optional[dict]] = {files[0]: first_info}

    # ════════════════════════════════════════════════════════════════════
    # Output mode
    # ════════════════════════════════════════════════════════════════════
    out_cfg = pick_output_mode(files, history)

    # For audio modes we always use a flat output dir (no in-place needed)
    if mode in ("2", "3"):
        flat_dir = out_cfg.base_dir if out_cfg.mode == "subfolder" else str(
            Path(files[0]).parent / "fftoolbox_output")
        os.makedirs(flat_dir, exist_ok=True)
        console.print(f"  [green]✓[/]  Output: [dim]{escape(flat_dir)}[/]")

    elif out_cfg.mode == "subfolder":
        console.print(f"  [green]✓[/]  Output: [dim]{escape(out_cfg.base_dir)}[/]")
        if out_cfg.batch_root and len(files) > 1:
            console.print(f"  [dim]  Subfolder structure preserved from: {escape(out_cfg.batch_root)}[/]")
    elif out_cfg.mode == "inplace_backup":
        console.print(
            f"  [green]✓[/]  In-place  ·  originals → [bold]<dir>/{out_cfg.backup_suffix}/[/]"
        )
    elif out_cfg.mode == "inplace":
        console.print("  [bold yellow]✓  In-place overwrite (no backup)[/]")

    # legacy alias used by audio sub-modes
    output_dir = flat_dir if mode in ("2","3") else (out_cfg.base_dir or "")

    # ════════════════════════════════════════════════════════════════════
    # AUDIO EXTRACTION / CONVERSION (modes 2 & 3)
    # ════════════════════════════════════════════════════════════════════
    if mode == "2":
        s, f = extract_audio(files, infos, output_dir)
        console.print()
        console.print(Rule("[bold]Summary[/]"))
        console.print(f"  [green]{s} succeeded[/]" + (f"  [red]{f} failed[/]" if f else ""))
        console.print(f"\n  [bold]Output:[/] [cyan]{escape(output_dir)}[/]")
        add_to_history(history, files, output_dir)
        return

    if mode == "3":
        audio_files = [f for f in files if Path(f).suffix.lower() in AUDIO_EXTENSIONS]
        if not audio_files:
            console.print("[red]  No audio files selected.[/]"); return
        s, f = convert_audio(audio_files, output_dir)
        console.print()
        console.print(Rule("[bold]Summary[/]"))
        console.print(f"  [green]{s} succeeded[/]" + (f"  [red]{f} failed[/]" if f else ""))
        console.print(f"\n  [bold]Output:[/] [cyan]{escape(output_dir)}[/]")
        add_to_history(history, files, output_dir)
        return

    # ════════════════════════════════════════════════════════════════════
    # RESOLVE QUICK FIX (mode 4)
    # ════════════════════════════════════════════════════════════════════
    if mode == "4":
        console.print()
        console.print(Rule("[bold]🔧  DaVinci Resolve Linux Audio Fix[/]"))
        preset      = deepcopy(PRESETS["resolve_audio_fix"])
        preset      = configure_preset("resolve_audio_fix", preset, first_info)
        selected_key = "resolve_audio_fix"

        console.print()
        if not Confirm.ask("[bold]Fix audio on all selected files now?[/]", default=True):
            console.print("[yellow]  Cancelled.[/]"); return

        success, failed = 0, 0
        for i, fpath in enumerate(files, 1):
            fi = infos.get(fpath) or run_ffprobe(fpath); infos[fpath] = fi
            if not fi:
                console.print(f"  [{i}] [red]Cannot read: {escape(Path(fpath).name)}[/]")
                failed += 1; continue
            console.print(f"\n  [bold][{i}/{len(files)}][/]  {escape(Path(fpath).name)}")

            out_path = out_cfg.output_path_for(fpath, "resolve_fix", ".mov")

            if out_cfg.mode == "inplace_backup":
                bak = out_cfg.prepare_inplace_backup(fpath)
                if bak: console.print(f"  [dim]  backed up → {escape(Path(bak).name)}[/]")

            out_path = _unique_path(out_path) if os.path.exists(out_path) and out_cfg.mode == "subfolder" else out_path

            ok, out_path = encode_file(fpath, out_path, preset, fi, i, len(files))
            if ok and os.path.exists(out_path):
                size_feedback(file_size_bytes(fi), out_path, selected_key)
                console.print(f"  [dim]{escape(out_path)}[/]")
                success += 1
            else:
                failed += 1

        console.print()
        console.print(Rule("[bold]Summary[/]"))
        console.print(f"  [green]{success} fixed[/]" + (f"  [red]{failed} failed[/]" if failed else ""))
        console.print(f"\n  [bold]Output:[/] [cyan]{escape(out_cfg.base_dir or '(in-place)')}[/]")
        console.print("  [dim]Import the .mov files into DaVinci Resolve — audio should work now.[/]")
        add_to_history(history, files, out_cfg.base_dir or str(Path(files[0]).parent))
        return

    # ════════════════════════════════════════════════════════════════════
    # VIDEO CONVERSION (mode 1) — preset selection
    # ════════════════════════════════════════════════════════════════════
    console.print()
    console.print(Rule("[bold]Step 2 · Choose Preset[/]"))
    console.print()
    suggested = suggest_preset(first_info) if first_info else "web_1080p"
    show_presets_table(suggested)

    preset_keys  = list(PRESETS.keys())
    suggested_no = str(preset_keys.index(suggested)+1)

    raw_c = Prompt.ask("Preset # (or 'i' to import)", default=suggested_no).strip().lower()

    if raw_c == "i":
        imported = import_preset_menu()
        if not imported: console.print("[yellow]  Import cancelled.[/]"); return
        selected_key = "_imported"; preset = imported
    elif raw_c.isdigit() and 1 <= int(raw_c) <= len(preset_keys):
        selected_key = preset_keys[int(raw_c)-1]
        preset       = deepcopy(PRESETS[selected_key])
        tip = preset.get("tip","")
        if tip: console.print(f"\n  [dim]💡 {tip}[/]")
        preset = configure_preset(selected_key, preset, first_info)
    else:
        console.print("[red]  Invalid choice.[/]"); return

    color = preset.get("color","cyan")
    console.print(f"\n  [green]✓[/]  [{color}]{preset.get('emoji','')} {preset.get('name','Custom')}[/]")

    # Preview option (single file only)
    console.print()
    if len(files) == 1 and first_info and preset.get("codec") != "copy":
        if Confirm.ask("  Run a 5-second preview encode with quality estimate?", default=False):
            if not run_preview(files[0], preset, first_info):
                console.print("[yellow]  Cancelled.[/]"); return

    # ── Encode plan ──────────────────────────────────────────────────────
    console.print()
    console.print(Rule("[bold]Encode Plan[/]"))
    sfx     = (selected_key if selected_key not in ("_imported","custom") else "custom")
    out_ext = preset.get("_output_ext",".mp4")

    plan_tbl = Table(box=box.SIMPLE, padding=(0,1))
    plan_tbl.add_column("File",     max_width=30, overflow="fold")
    plan_tbl.add_column("Size",     style="dim", width=10)
    plan_tbl.add_column("Duration", style="dim", width=10)
    plan_tbl.add_column("Res",      style="dim", width=12)
    plan_tbl.add_column("→ Output", max_width=30, overflow="fold")
    total_src = 0

    for f in files:
        fi = infos.get(f) or run_ffprobe(f); infos[f] = fi
        out_preview = out_cfg.output_path_for(f, sfx, out_ext)
        out_label   = (
            f"[dim](in-place)[/]"
            if out_cfg.mode in ("inplace","inplace_backup")
            else escape(Path(out_preview).name)
        )
        if fi:
            sz  = file_size_bytes(fi); dur = file_duration(fi)
            vs  = video_stream(fi)
            w   = (vs or {}).get("width","?"); h = (vs or {}).get("height","?")
            total_src += sz
            plan_tbl.add_row(Path(f).name, human_size(sz), human_dur(dur), f"{w}×{h}", out_label)
        else:
            plan_tbl.add_row(Path(f).name,"?","?","?",out_label)

    console.print(plan_tbl)
    if total_src > 0:
        console.print(f"  [dim]Total input: {human_size(total_src)}[/]")
    if out_cfg.mode == "inplace_backup":
        console.print(
            f"  [bold yellow]⚠  Originals will be moved to "
            f"<dir>/{out_cfg.backup_suffix}/ before encoding.[/]"
        )
    elif out_cfg.mode == "inplace":
        console.print("  [bold red]⚠  Originals will be overwritten with no backup![/]")

    console.print()
    if not Confirm.ask("[bold]Start encoding?[/]", default=True):
        console.print("[yellow]  Cancelled.[/]"); return

    # ── Encode ───────────────────────────────────────────────────────────
    console.print()
    console.print(Rule("[bold cyan]Encoding[/]"))
    success, failed = 0, 0
    results: List[Tuple[str,str,int,int]] = []

    for i, fpath in enumerate(files, 1):
        console.print()
        # Show relative path when we have a batch root
        if out_cfg.batch_root:
            try:
                display_name = str(Path(fpath).relative_to(out_cfg.batch_root))
            except ValueError:
                display_name = Path(fpath).name
        else:
            display_name = Path(fpath).name
        console.print(f"  [bold][{i}/{len(files)}][/]  {escape(display_name)}")

        fi = infos.get(fpath) or run_ffprobe(fpath)
        if not fi:
            console.print("  [red]  Cannot read file — skipping[/]"); failed += 1; continue

        # Per-file percent target
        file_preset = deepcopy(preset)
        if preset.get("_pct") and file_size_bytes(fi) > 0 and file_duration(fi) > 0:
            file_preset["target_mb"] = file_size_bytes(fi)/1024/1024 * preset["_pct"]

        src_sz = file_size_bytes(fi)

        # For in-place modes: backup original first, then encode to original path
        if out_cfg.mode == "inplace_backup":
            bak = out_cfg.prepare_inplace_backup(fpath)
            if bak is None:
                console.print("  [red]  Backup failed — skipping to protect original.[/]")
                failed += 1; continue
            console.print(f"  [dim]  → backup: {escape(Path(bak).name)}[/]")
            # Encode from the backup (original was moved there)
            src_for_encode = bak
            out_path       = out_cfg.output_path_for(fpath, sfx, out_ext)
        elif out_cfg.mode == "inplace":
            src_for_encode = fpath
            out_path       = out_cfg.output_path_for(fpath, sfx, out_ext)
            # Encode to a temp file first, then move over original on success
            tmp_out = out_path + ".fftoolbox_tmp" + out_ext
            out_path = tmp_out
        else:
            src_for_encode = fpath
            out_path       = out_cfg.output_path_for(fpath, sfx, out_ext)
            if os.path.exists(out_path):
                out_path = handle_collision(out_path)
                if out_path is None:
                    console.print("  [dim]  Skipped.[/]"); continue

        try:
            ok, out_path = encode_file(src_for_encode, out_path, file_preset, fi, i, len(files))
        except Exception as exc:
            console.print(f"  [red]  Error: {exc}[/]")
            if os.environ.get("FFTOOLBOX_DEBUG"):
                console.print(f"  [dim]{traceback.format_exc()}[/]")
            ok = False; out_path = out_path or ""

        # For inplace overwrite: move temp file over original on success
        if out_cfg.mode == "inplace" and ok and out_path.endswith(".fftoolbox_tmp" + out_ext):
            final_path = out_cfg.output_path_for(fpath, sfx, out_ext)
            try:
                shutil.move(out_path, final_path)
                out_path = final_path
            except Exception as e:
                console.print(f"  [red]  Could not finalize: {e}[/]")
                ok = False

        if ok and os.path.exists(out_path):
            dst_sz = os.path.getsize(out_path)
            size_feedback(src_sz, out_path, selected_key)
            console.print(f"  [dim]{escape(out_path)}[/]")
            success += 1; results.append((fpath, out_path, src_sz, dst_sz))
        else:
            # If inplace_backup failed after backup, restore original
            if out_cfg.mode == "inplace_backup" and 'bak' in dir() and bak and os.path.exists(bak):
                try:
                    shutil.move(bak, fpath)
                    console.print(f"  [yellow]  Encode failed — original restored.[/]")
                except Exception:
                    console.print(f"  [red]  Encode failed & could not restore: {escape(bak)}[/]")
            failed += 1

    # ── Summary ──────────────────────────────────────────────────────────
    console.print()
    console.print(Rule("[bold]Summary[/]"))
    parts = [f"[green]✓ {success} succeeded[/]"]
    if failed: parts.append(f"[red]✗ {failed} failed[/]")
    console.print("  " + "  |  ".join(parts))

    if results:
        tin   = sum(r[2] for r in results)
        tout  = sum(r[3] for r in results)
        saved = tin - tout
        pct   = (saved/tin*100) if tin > 0 else 0
        clr   = "green" if saved > 0 else "yellow"
        console.print(
            f"  Total  {human_size(tin)} → [{clr}]{human_size(tout)}[/]"
            + (f"  [green](saved {human_size(saved)}, {pct:.1f}%)[/]" if saved > 0
               else f"  [yellow](+{human_size(-saved)} larger)[/]")
        )

    out_summary = out_cfg.base_dir if out_cfg.mode == "subfolder" else "(in-place)"
    console.print(f"\n  [bold]Output:[/] [cyan]{escape(out_summary)}[/]")

    add_to_history(history, files,
                   out_cfg.base_dir or str(Path(files[0]).parent))
    console.print()


if __name__ == "__main__":
    # ── CLI flags ────────────────────────────────────────────────────────
    if "--update" in sys.argv or "-u" in sys.argv:
        _ensure_rich()
        from rich.console import Console as _C; _c = _C(highlight=False)
        _c.print(f"\n[bold cyan]fftoolbox[/] [dim]v{APP_VERSION}[/]  — checking for updates …\n")
        _fetch_update_info()          # run synchronously when called explicitly
        if _update_info.available:
            perform_update(interactive=True)
        else:
            _c.print(f"[green]✓  You are on the latest version (v{APP_VERSION}).[/]\n")
        sys.exit(0)

    try:
        main()
    except KeyboardInterrupt:
        console.print("\n\n  [yellow]Aborted.[/]")
        sys.exit(1)
