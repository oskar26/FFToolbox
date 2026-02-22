#!/usr/bin/env python3
"""
fftoolbox Pro — Smart Video Converter  v1.1
===========================================
Run:  python3 fftoolbox_pro.py
Cmd:  sudo cp fftoolbox_pro.py /usr/local/bin/fftoolbox && sudo chmod +x /usr/local/bin/fftoolbox

Requirements: Python 3.8+, ffmpeg + ffprobe in PATH
License: MIT
"""

import sys, os, re, json, math, time, shutil, tempfile, subprocess, traceback, hashlib
from pathlib import Path
from datetime import timedelta
from typing import Optional, List, Tuple, Dict, Any
from urllib.request import urlopen, Request
from urllib.error import URLError

# ── auto-install rich ────────────────────────────────────────────────────────
def _ensure_rich():
    try:
        import rich
    except ImportError:
        print("Installing 'rich' …")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "rich", "--quiet"],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("Done.\n")
        except Exception as e:
            print(f"ERROR: pip install rich failed: {e}\nRun: pip install rich"); sys.exit(1)
_ensure_rich()

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.rule import Rule
from rich.progress import Progress, BarColumn, TextColumn, TaskProgressColumn, SpinnerColumn
from rich.prompt import Prompt, Confirm
from rich import box
from rich.align import Align
from rich.markup import escape

console = Console(highlight=False)

APP_VERSION    = "1.1"
APP_NAME       = "fftoolbox"
GITHUB_RAW_URL = "https://raw.githubusercontent.com/yourusername/fftoolbox/main/VERSION"
PRESETS_DIR    = Path.home() / ".config" / "fftoolbox" / "presets"

# File size safety margin: target × SAFETY = actual bitrate target
# Ensures output never EXCEEDS entered value (container overhead, audio variance, etc.)
BITRATE_SAFETY = 0.96

WHATSAPP_VIDEO_MB = 100

VIDEO_EXTENSIONS = {
    ".mp4",".mov",".mkv",".m4v",".avi",".wmv",".flv",".webm",
    ".mxf",".ts",".mts",".m2ts",".mpg",".mpeg",".3gp",".ogv",".dv",".vob",
}
PROFESSIONAL_CODECS = {
    "prores","prores_ks","dnxhd","dnxhr","mjpeg","v210",
    "r10k","r210","cineform","cfhd","huffyuv","ffv1","utvideo",
}
RESOLUTIONS = [
    (None,  None,  "Keep original"),
    (3840,  2160,  "4K UHD   (3840 x 2160)"),
    (2560,  1440,  "1440p    (2560 x 1440)"),
    (1920,  1080,  "1080p    (1920 x 1080)"),
    (1280,  720,   "720p     (1280 x 720)"),
    (854,   480,   "480p     (854 x 480)"),
    (640,   360,   "360p     (640 x 360)"),
    (426,   240,   "240p     (426 x 240)"),
    (256,   144,   "144p     (256 x 144)"),
]

# ════════════════════════════════════════════════════════════════════════
# PRESETS
# ════════════════════════════════════════════════════════════════════════
PRESETS: Dict[str, Dict[str, Any]] = {
    "smart": {
        "group":"⭐  Smart","name":"Smart Recommended (auto-optimized)","emoji":"🧠",
        "desc":"Analyzes your video and computes the ideal CRF + resolution automatically",
        "codec":"libx264","crf":None,"speed":"slow","audio_codec":"aac","audio_kbps":128,
        "max_res":None,"target_mb":None,"two_pass":False,"color":"bold cyan",
        "tip":"Calculates the optimal balance of quality and file size for YOUR specific video.",
    },
    "whatsapp": {
        "group":"📤  Sharing","name":"WhatsApp  (< 100 MB, 720p)","emoji":"📱",
        "desc":"Two-pass · stays safely under 100 MB · 720p · H.264 · AAC",
        "codec":"libx264","crf":None,"speed":"slow","audio_codec":"aac","audio_kbps":96,
        "max_res":(1280,720),"target_mb":95,"two_pass":True,"color":"green",
        "tip":"WhatsApp video preview limit is 100 MB. Two-pass ensures you stay under.",
    },
    "telegram": {
        "group":"📤  Sharing","name":"Telegram  (1080p, great quality)","emoji":"✈️",
        "desc":"1080p max · H.264 CRF 22 · AAC 192 · Telegram supports up to 2 GB",
        "codec":"libx264","crf":22,"speed":"slow","audio_codec":"aac","audio_kbps":192,
        "max_res":(1920,1080),"target_mb":None,"two_pass":False,"color":"bright_blue",
        "tip":"Telegram keeps quality intact. Supports up to 2 GB.",
    },
    "resolve_cleanup": {
        "group":"🎬  Professional","name":"DaVinci Resolve Cleanup","emoji":"🎬",
        "desc":"ProRes / DNxHR  ->  H.264 · CRF 18 · near-lossless · keeps 4K",
        "codec":"libx264","crf":18,"speed":"slow","audio_codec":"aac","audio_kbps":192,
        "max_res":None,"target_mb":None,"two_pass":False,"color":"cyan",
        "tip":"CRF 18 = near-lossless. Shrinks 10 GB Resolve exports to 200–800 MB.",
    },
    "archive_h265": {
        "group":"🎬  Professional","name":"Archive  (H.265 / HEVC)","emoji":"🗄️",
        "desc":"CRF 18 · ~40 % smaller than H.264 · Apple HVC1 tag · long-term",
        "codec":"libx265","crf":18,"speed":"slow","audio_codec":"aac","audio_kbps":192,
        "max_res":None,"target_mb":None,"two_pass":False,"color":"blue",
        "tip":"Best long-term archive format. Compatible with modern devices.",
    },
    "web_1080p": {
        "group":"🌐  Web","name":"Web / Social Media  (1080p)","emoji":"🌐",
        "desc":"H.264 · CRF 23 · 1080p max · fast-start · YouTube / Vimeo / Instagram",
        "codec":"libx264","crf":23,"speed":"slow","audio_codec":"aac","audio_kbps":128,
        "max_res":(1920,1080),"target_mb":None,"two_pass":False,"color":"yellow",
        "tip":"Safe choice for any online platform.",
    },
    "compress_light": {
        "group":"📦  Compression","name":"Compress Light  (~25 % smaller)","emoji":"🟢",
        "desc":"CRF 20 · barely noticeable quality loss · ~25 % smaller",
        "codec":"libx264","crf":20,"speed":"medium","audio_codec":"aac","audio_kbps":192,
        "max_res":None,"target_mb":None,"two_pass":False,"color":"bright_green",
        "tip":"Almost imperceptible quality difference.",
    },
    "compress_medium": {
        "group":"📦  Compression","name":"Compress Medium  (~50 % smaller)","emoji":"🟡",
        "desc":"CRF 26 · noticeable but very watchable · ~50 % smaller",
        "codec":"libx264","crf":26,"speed":"medium","audio_codec":"aac","audio_kbps":128,
        "max_res":None,"target_mb":None,"two_pass":False,"color":"yellow",
        "tip":"Good balance of size and quality.",
    },
    "compress_heavy": {
        "group":"📦  Compression","name":"Compress Heavy  (~75 % smaller)","emoji":"🔴",
        "desc":"CRF 32 · clear quality loss · 720p max · ~75 % smaller",
        "codec":"libx264","crf":32,"speed":"fast","audio_codec":"aac","audio_kbps":64,
        "max_res":(1280,720),"target_mb":None,"two_pass":False,"color":"red",
        "tip":"Maximum compression. Pixelation may be visible.",
    },
    "target_mb": {
        "group":"🎯  Exact Control","name":"Target Exact File Size  (MB)","emoji":"📐",
        "desc":"Enter target MB  ->  two-pass · 96 % safety margin · never exceeds target",
        "codec":"libx264","crf":None,"speed":"slow","audio_codec":"aac","audio_kbps":128,
        "max_res":None,"target_mb":None,"two_pass":True,"color":"magenta",
        "tip":"Uses 96 % safety margin so output is always UNDER your target.",
    },
    "target_percent": {
        "group":"🎯  Exact Control","name":"Target % Compression","emoji":"📊",
        "desc":"Enter % of original size you want  ->  auto bitrate + two-pass",
        "codec":"libx264","crf":None,"speed":"slow","audio_codec":"aac","audio_kbps":128,
        "max_res":None,"target_mb":None,"two_pass":True,"color":"magenta",
        "tip":"E.g. 30  ->  output is ~30 % of original size.",
    },
    "quick": {
        "group":"⚡  Utility","name":"Quick Convert  (fast encode)","emoji":"⚡",
        "desc":"H.264 · CRF 23 · medium speed",
        "codec":"libx264","crf":23,"speed":"medium","audio_codec":"aac","audio_kbps":128,
        "max_res":None,"target_mb":None,"two_pass":False,"color":"bright_yellow",
        "tip":"Fast encode. Good quality. Ideal for batch jobs.",
    },
    "fix_audio": {
        "group":"⚡  Utility","name":"Fix Audio  (copy video)","emoji":"🔊",
        "desc":"Video stream copied unchanged · audio  ->  AAC 192 · instant",
        "codec":"copy","crf":None,"speed":None,"audio_codec":"aac","audio_kbps":192,
        "max_res":None,"target_mb":None,"two_pass":False,"color":"white",
        "tip":"Almost instant — only audio is processed.",
    },
    "custom": {
        "group":"⚙️   Custom","name":"Custom — full manual control","emoji":"⚙️",
        "desc":"Configure every parameter yourself",
        "codec":None,"crf":None,"speed":None,"audio_codec":None,"audio_kbps":None,
        "max_res":None,"target_mb":None,"two_pass":False,"color":"dim white",
        "tip":"Full control: codec, CRF, speed, resolution, audio, hardware encoders.",
    },
}

# ════════════════════════════════════════════════════════════════════════
# SYSTEM / FFPROBE HELPERS
# ════════════════════════════════════════════════════════════════════════

def check_deps():
    return bool(shutil.which("ffmpeg")), bool(shutil.which("ffprobe"))

def run_ffprobe(path: str) -> Optional[dict]:
    cmd = ["ffprobe","-v","error","-print_format","json","-show_format","-show_streams",path]
    try:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           check=True, text=True, timeout=30)
        return json.loads(r.stdout)
    except subprocess.TimeoutExpired:
        console.print("[red]  ffprobe timed out[/]"); return None
    except (json.JSONDecodeError, subprocess.CalledProcessError) as e:
        console.print(f"[red]  ffprobe failed: {str(e)[:120]}[/]"); return None

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

def file_duration(info: dict) -> float:
    vs = video_stream(info)
    if vs and vs.get("duration"):
        try: return float(vs["duration"])
        except: pass
    try: return float(info.get("format",{}).get("duration") or 0)
    except: return 0.0

def file_size_bytes(info: dict) -> int:
    try: return int(info.get("format",{}).get("size") or 0)
    except: return 0

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
        v = int(n)/int(d)
        return f"{v:.3g} fps"
    except: return raw or "?"

def is_professional(info: dict) -> bool:
    vs = video_stream(info)
    vc = (vs or {}).get("codec_name","").lower()
    return any(p in vc for p in PROFESSIONAL_CODECS)

def scale_vf(src_w: int, src_h: int, max_res: Tuple[int,int]) -> Optional[str]:
    mw, mh = max_res
    if src_w <= mw and src_h <= mh: return None
    ratio = min(mw/src_w, mh/src_h)
    nw = (int(src_w*ratio)//2)*2
    nh = (int(src_h*ratio)//2)*2
    return f"scale={nw}:{nh}:flags=lanczos"

def target_video_kbps(target_mb: float, duration_s: float, audio_kbps: int,
                      safety: float = BITRATE_SAFETY) -> int:
    """
    Compute video bitrate to stay UNDER target_mb.
    - safety=0.96 means we target 96% of desired bitrate
    - This accounts for container overhead, B-frame overhead, audio variance
    Result is always safe margin below the user's specified target.
    """
    bits    = target_mb * 8 * 1024 * 1024 * safety
    kbps_t  = bits / max(duration_s, 1) / 1000
    return max(80, int(kbps_t - audio_kbps))

def parse_progress_time(line: str) -> Optional[float]:
    m = re.search(r"time=(\d+):(\d+):([\d.]+)", line)
    if m: return int(m.group(1))*3600 + int(m.group(2))*60 + float(m.group(3))
    return None

# ════════════════════════════════════════════════════════════════════════
# HARDWARE ENCODER DETECTION + FALLBACK
# ════════════════════════════════════════════════════════════════════════

def detect_hw_encoders() -> List[Tuple[str,str]]:
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
        return [(e,l) for e,l in candidates if e in out]
    except: return []

def hw_encoder_fallback(preferred_codec: str, input_path: str) -> str:
    """
    Test if a hardware encoder actually works with a 1-second probe encode.
    Falls back to libx264/libx265 if HW encoder fails.
    Returns the encoder that will actually work.
    """
    hw_names = {"nvenc","vaapi","qsv","videotoolbox","amf"}
    if not any(h in preferred_codec for h in hw_names):
        return preferred_codec  # software encoder, no test needed

    console.print(f"  [dim]Testing hardware encoder {preferred_codec} …[/]")
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tf:
        tmp_out = tf.name
    try:
        test_cmd = [
            "ffmpeg","-hide_banner","-y","-i",input_path,
            "-t","1","-vf","scale=320:180",
            "-c:v",preferred_codec,"-an",tmp_out,
        ]
        r = subprocess.run(test_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        if r.returncode == 0:
            console.print(f"  [green]  HW encoder {preferred_codec} OK[/]")
            return preferred_codec
        else:
            raise RuntimeError("non-zero exit")
    except Exception:
        # Determine fallback
        fallback = "libx265" if "hevc" in preferred_codec else "libx264"
        console.print(f"  [yellow]  HW encoder failed — falling back to {fallback}[/]")
        return fallback
    finally:
        try: os.unlink(tmp_out)
        except: pass

# ════════════════════════════════════════════════════════════════════════
# SMART PRESET — auto-compute optimal CRF + resolution
# ════════════════════════════════════════════════════════════════════════

def compute_smart_preset(info: dict) -> dict:
    """
    Analyzes source video and returns a custom preset with optimal CRF and resolution.
    Logic:
      - Estimate effective bitrate per pixel
      - If source is already well-compressed → use copy-ish CRF
      - If source is bloated (ProRes/uncompressed) → aggressive CRF
      - Pick resolution that makes sense for the bitrate
    """
    preset  = dict(PRESETS["smart"])
    vs      = video_stream(info)
    dur     = file_duration(info)
    sz      = file_size_bytes(info)
    src_w   = safe_int((vs or {}).get("width",1920))
    src_h   = safe_int((vs or {}).get("height",1080))
    src_bps = safe_int((vs or {}).get("bit_rate")) or (sz*8/max(dur,1) if dur>0 else 0)
    src_kbps = src_bps / 1000

    # Bits per pixel per second (bpp) — measure of compression efficiency
    pixels   = src_w * src_h
    bpp      = src_kbps / pixels if pixels > 0 else 0

    # CRF selection based on source compression level
    if bpp > 0.5:          # very uncompressed (ProRes, raw) → aggressive
        crf = 18
    elif bpp > 0.1:        # mildly compressed
        crf = 20
    elif bpp > 0.04:       # typical camera h264
        crf = 22
    elif bpp > 0.02:       # already well compressed
        crf = 24
    else:                  # very low bitrate source
        crf = 26

    # Resolution: if 4K at low bpp → recommend 1080p
    recommended_res = None
    if src_w >= 3840 and bpp < 0.05:
        recommended_res = (1920, 1080)
        console.print("  [dim]Smart: 4K source at low bitrate → recommending 1080p downscale[/]")
    elif src_w >= 2560 and bpp < 0.04:
        recommended_res = (1920, 1080)
        console.print("  [dim]Smart: 1440p source at moderate bitrate → recommending 1080p[/]")
    elif src_w >= 1920 and src_kbps < 1500:
        recommended_res = (1280, 720)
        console.print("  [dim]Smart: 1080p source at low bitrate → recommending 720p[/]")

    # Estimated output size
    if dur > 0:
        # Estimate output kbps with H.264 at chosen CRF
        # Rule of thumb: CRF 18 ≈ 60% of uncompressed, CRF 23 ≈ 30%
        est_ratio  = 0.6 * (0.75 ** (crf - 18))  # rough exponential scaling
        est_kbps   = src_kbps * est_ratio
        est_mb     = est_kbps * 1000 * dur / (8 * 1024 * 1024)
        console.print(
            f"  [dim]Smart analysis: source {src_kbps:.0f} kb/s · bpp={bpp:.4f} · "
            f"recommended CRF {crf} → est. ~{est_mb:.0f} MB[/]"
        )

    preset["crf"]     = crf
    preset["max_res"] = recommended_res
    preset["speed"]   = "slow"
    preset["audio_codec"]  = "aac"
    preset["audio_kbps"]   = 128
    preset["two_pass"]     = False
    preset["_smart_crf"]   = crf
    preset["_smart_res"]   = recommended_res

    return preset

# ════════════════════════════════════════════════════════════════════════
# SMART RESOLUTION RECOMMENDATION for target-size presets
# ════════════════════════════════════════════════════════════════════════

def recommend_resolution_for_target(target_mb: float, duration_s: float,
                                    audio_kbps: int, src_w: int, src_h: int
                                    ) -> Tuple[Optional[Tuple[int,int]], str]:
    """
    Given a target file size, compute the optimal resolution.
    Returns (resolution_tuple_or_None, explanation_string)
    """
    if duration_s <= 0:
        return None, "Cannot compute — unknown duration"

    vkbps = target_video_kbps(target_mb, duration_s, audio_kbps)

    # Minimum acceptable bpp for good-looking H.264:
    # 720p needs ~500+ kb/s, 1080p needs ~1500+ kb/s, 4K needs ~8000+ kb/s
    thresholds = [
        (3840, 2160, 8000, "4K"),
        (2560, 1440, 4000, "1440p"),
        (1920, 1080, 1500, "1080p"),
        (1280, 720,  500,  "720p"),
        (854,  480,  200,  "480p"),
        (640,  360,  100,  "360p"),
    ]
    best_res = None
    best_label = "360p"
    for w, h, min_kbps, label in thresholds:
        if vkbps >= min_kbps and src_w >= w and src_h >= h:
            best_res   = (w, h) if (w < src_w or h < src_h) else None
            best_label = label
            break

    explanation = (
        f"video ~{vkbps} kb/s at {target_mb:.0f} MB → "
        f"recommended: [bold]{best_label}[/]"
        + (f" ({best_res[0]}x{best_res[1]})" if best_res else " (keep original)")
    )
    return best_res, explanation

# ════════════════════════════════════════════════════════════════════════
# ENCODING PREVIEW (5-second test clip)
# ════════════════════════════════════════════════════════════════════════

def run_preview_encode(input_path: str, preset: dict, info: dict) -> bool:
    """
    Encode a 5-second clip from the middle of the video.
    Shows resulting file size, estimated PSNR quality.
    Returns True if user wants to proceed with full encode.
    """
    dur = file_duration(info)
    vs  = video_stream(info)
    src_w = safe_int((vs or {}).get("width",1920))  if vs else 1920
    src_h = safe_int((vs or {}).get("height",1080)) if vs else 1080

    # Start at 30% of video (skip intros)
    start  = max(0, dur * 0.3)
    length = min(5.0, dur * 0.1, 10.0)

    if length < 1:
        console.print("  [dim]Video too short for preview — skipping[/]")
        return True

    console.print(f"\n  [bold cyan]Preview Encode[/]  [dim](encoding {length:.0f}s from {human_dur(start)})[/]")

    tmpdir   = tempfile.mkdtemp(prefix="fftoolbox_preview_")
    tmp_in   = input_path
    tmp_out  = os.path.join(tmpdir, "preview.mp4")
    tmp_ref  = os.path.join(tmpdir, "reference.mp4")

    try:
        # Build command — same as full encode but with time limit
        from copy import deepcopy
        p2    = deepcopy(preset)
        p2["two_pass"] = False  # no two-pass for preview
        if p2.get("target_mb"):
            # Estimate CRF for preview
            p2["crf"]       = 23
            p2["target_mb"] = None

        vf_list = build_vf_list(p2, src_w, src_h)
        cmd = ["ffmpeg","-hide_banner","-y","-ss",str(start),"-t",str(length),"-i",input_path]
        if vf_list: cmd += ["-vf",",".join(vf_list)]
        cmd += ["-map","0:v","-map","0:a?"]

        co = p2.get("codec") or "libx264"
        if co == "copy" or co is None: co = "libx264"
        if co == "libx264":
            cmd += ["-c:v","libx264","-profile:v","high","-pix_fmt","yuv420p"]
        elif co == "libx265":
            cmd += ["-c:v","libx265","-pix_fmt","yuv420p"]
        else:
            cmd += ["-c:v",co,"-pix_fmt","yuv420p"]

        crf = p2.get("crf") or 23
        cmd += ["-crf",str(crf)]
        sp  = p2.get("speed") or "fast"
        if not any(h in co for h in {"nvenc","vaapi","qsv","videotoolbox","amf"}):
            cmd += ["-preset",sp]

        ac = p2.get("audio_codec") or "aac"
        ab = p2.get("audio_kbps") or 128
        if ac not in ("copy","flac"): cmd += ["-c:a",ac,"-b:a",f"{ab}k"]
        else: cmd += ["-c:a",ac]

        cmd += [tmp_out]

        with console.status("[cyan]Encoding preview …[/]"):
            r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)

        if r.returncode != 0 or not os.path.exists(tmp_out):
            console.print("  [yellow]Preview encode failed — continuing with full encode[/]")
            return True

        prev_sz   = os.path.getsize(tmp_out)
        prev_kbps = (prev_sz*8/length/1000) if length > 0 else 0

        # Estimate full output size based on preview bitrate
        if preset.get("target_mb"):
            est_full_mb = preset["target_mb"]
        elif dur > 0:
            est_full_mb = prev_kbps * 1000 * dur / (8*1024*1024)
        else:
            est_full_mb = 0

        # Try to get PSNR via ffmpeg (quick reference encode at high quality)
        psnr_str = ""
        try:
            ref_cmd = ["ffmpeg","-hide_banner","-y","-ss",str(start),"-t",str(length),
                       "-i",input_path,"-c:v","libx264","-crf","0","-preset","ultrafast",
                       "-an",tmp_ref]
            rr = subprocess.run(ref_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
            if rr.returncode == 0:
                psnr_cmd = ["ffmpeg","-hide_banner","-i",tmp_out,"-i",tmp_ref,
                            "-lavfi","psnr","-f","null","-"]
                pr = subprocess.run(psnr_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                    text=True, timeout=30)
                m = re.search(r"average:([\d.]+)", pr.stderr)
                if m:
                    psnr_val = float(m.group(1))
                    if psnr_val >= 45:   quality = "[green]Excellent[/]"
                    elif psnr_val >= 40: quality = "[green]Very Good[/]"
                    elif psnr_val >= 35: quality = "[yellow]Good[/]"
                    elif psnr_val >= 30: quality = "[yellow]Acceptable[/]"
                    else:                quality = "[red]Poor[/]"
                    psnr_str = f"  PSNR {psnr_val:.1f} dB = {quality}"
        except Exception:
            pass  # PSNR is optional

        # Show results
        tbl = Table(box=box.ROUNDED, border_style="dim", show_header=False, padding=(0,1))
        tbl.add_column("K", style="bold cyan", width=20)
        tbl.add_column("V")
        tbl.add_row("Preview duration",  f"{length:.0f}s")
        tbl.add_row("Preview size",       human_size(prev_sz))
        tbl.add_row("Preview bitrate",    f"{prev_kbps:.0f} kb/s")
        if est_full_mb > 0:
            clr = "green" if not preset.get("target_mb") or est_full_mb <= preset["target_mb"] else "yellow"
            tbl.add_row("Estimated full output", f"[{clr}]~{est_full_mb:.0f} MB[/]")
        if psnr_str:
            tbl.add_row("Quality (PSNR)", psnr_str)
        console.print(Panel(tbl, title="[bold]Preview Result[/]", border_style="cyan"))

        return Confirm.ask("  Proceed with full encode?", default=True)

    except Exception as e:
        console.print(f"  [yellow]Preview failed ({e}) — continuing[/]")
        return True
    finally:
        try: shutil.rmtree(tmpdir)
        except: pass

# ════════════════════════════════════════════════════════════════════════
# OUTPUT COLLISION HANDLING
# ════════════════════════════════════════════════════════════════════════

def handle_collision(out_path: str) -> Optional[str]:
    """
    Called when output file already exists.
    Returns new path, or None to skip this file.
    """
    console.print(f"\n  [yellow]! File already exists:[/]  [dim]{escape(out_path)}[/]")
    console.print("  [cyan]1[/]  Overwrite")
    console.print("  [cyan]2[/]  Auto-rename  (_1, _2, …)")
    console.print("  [cyan]3[/]  Enter custom name")
    console.print("  [cyan]4[/]  Skip this file")

    c = Prompt.ask("  Choice", choices=["1","2","3","4"], default="2")

    if c == "1":
        return out_path
    if c == "2":
        stem = Path(out_path).stem
        ext  = Path(out_path).suffix
        d    = Path(out_path).parent
        for i in range(1, 10000):
            candidate = str(d / f"{stem}_{i}{ext}")
            if not os.path.exists(candidate):
                return candidate
        return str(d / f"{stem}_{int(time.time())}{ext}")
    if c == "3":
        raw = Prompt.ask("  New filename (without extension)").strip()
        if not raw:
            return None
        new = str(Path(out_path).parent / f"{raw}.mp4")
        if os.path.exists(new):
            console.print(f"  [red]  '{escape(new)}' also exists — using auto-rename[/]")
            return handle_collision(new)
        return new
    return None  # skip

# ════════════════════════════════════════════════════════════════════════
# PRESET IMPORT / EXPORT
# ════════════════════════════════════════════════════════════════════════

def export_preset(preset: dict, name: str) -> None:
    PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^\w\-]", "_", name.strip())
    path = PRESETS_DIR / f"{safe_name}.json"
    exportable = {k: v for k, v in preset.items() if not k.startswith("_")}
    exportable["_fftoolbox_version"] = APP_VERSION
    exportable["_export_name"]       = name
    with open(path, "w") as f:
        json.dump(exportable, f, indent=2)
    console.print(f"  [green]Preset exported:[/] [dim]{path}[/]")

def import_preset_menu() -> Optional[Dict[str, Any]]:
    PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(PRESETS_DIR.glob("*.json"))
    if not files:
        console.print(f"  [dim]No saved presets found in {PRESETS_DIR}[/]")
        return None

    console.print("\n[bold cyan]Saved Presets[/]")
    tbl = Table(box=box.SIMPLE, padding=(0,1), show_header=False)
    tbl.add_column("#", style="bold dim", width=3)
    tbl.add_column("Name")
    tbl.add_column("Details", style="dim")
    for i, f in enumerate(files, 1):
        try:
            with open(f) as fh:
                d = json.load(fh)
            detail = f"codec={d.get('codec','?')} crf={d.get('crf','?')} v{d.get('_fftoolbox_version','?')}"
        except:
            detail = "?"
        tbl.add_row(str(i), d.get("_export_name", f.stem), detail)
    console.print(tbl)

    choices = [str(i) for i in range(1, len(files)+1)]
    c = Prompt.ask("Load preset #", choices=choices)
    try:
        with open(files[int(c)-1]) as fh:
            loaded = json.load(fh)
        loaded.setdefault("name",  loaded.get("_export_name","Imported"))
        loaded.setdefault("emoji", "📥")
        loaded.setdefault("color", "white")
        loaded.setdefault("tip",   "Imported preset")
        loaded.setdefault("group", "Imported")
        console.print(f"  [green]Loaded preset: {loaded.get('_export_name','?')}[/]")
        return loaded
    except Exception as e:
        console.print(f"[red]  Failed to load: {e}[/]"); return None

# ════════════════════════════════════════════════════════════════════════
# AUTO-UPDATER
# ════════════════════════════════════════════════════════════════════════

def check_for_update(timeout: float = 2.0) -> None:
    """Check GitHub for a newer version. Silent if network unavailable."""
    try:
        req = Request(GITHUB_RAW_URL, headers={"User-Agent": f"fftoolbox/{APP_VERSION}"})
        with urlopen(req, timeout=timeout) as resp:
            remote = resp.read().decode().strip()
        if remote and remote != APP_VERSION:
            console.print(
                Panel(
                    f"[bold yellow]Update available: v{remote}[/]\n"
                    f"[dim]You have v{APP_VERSION}. Get the latest at:[/]\n"
                    "https://github.com/yourusername/fftoolbox",
                    border_style="yellow", title="[yellow]Update[/]",
                )
            )
    except (URLError, OSError):
        pass  # no network — silent

# ════════════════════════════════════════════════════════════════════════
# UI HELPERS
# ════════════════════════════════════════════════════════════════════════

def print_banner():
    console.print()
    console.print(Panel.fit(
        Align.center(
            f"[bold cyan]{APP_NAME}[/][bold white] Pro[/]  [dim]v{APP_VERSION}[/]  [dim]|[/]  "
            "[italic]Smart Video Converter[/]\n"
            "[dim]Powered by FFmpeg  ·  Professional Terminal Interface[/]"
        ),
        border_style="cyan", padding=(0,6),
    ))
    console.print()

def print_file_info(info: dict, path: str):
    vs  = video_stream(info)
    dur = file_duration(info)
    sz  = file_size_bytes(info)
    vc  = (vs or {}).get("codec_name","?").upper()
    as_ = audio_stream(info)
    ac  = (as_ or {}).get("codec_name","?").upper()

    tbl = Table(box=box.ROUNDED, border_style="dim", show_header=False, padding=(0,1))
    tbl.add_column("K", style="bold cyan", width=16)
    tbl.add_column("V", style="white")
    tbl.add_row("Filename",  escape(Path(path).name))
    tbl.add_row("Size",      human_size(sz))
    tbl.add_row("Duration",  human_dur(dur))
    if vs:
        w = vs.get("width","?"); h = vs.get("height","?")
        tbl.add_row("Resolution", f"{w} x {h}")
        tbl.add_row("FPS",        fps_str(vs))
        bit = vs.get("bit_rate")
        if bit: tbl.add_row("Video bitrate", f"{int(bit)//1000} kb/s")
    vc_display = vc
    if any(p in vc.lower() for p in PROFESSIONAL_CODECS):
        vc_display = f"[bold yellow]! {vc}  (professional codec — large file)[/]"
    tbl.add_row("Video codec", vc_display)
    na = len(all_audio_streams(info))
    tbl.add_row("Audio codec", f"{ac}" + (f"  ({na} tracks)" if na > 1 else ""))
    if sz > 500*1024*1024:
        tbl.add_row("[yellow]Tip[/]","[yellow]Large file — [bold]DaVinci Resolve Cleanup[/] preset suggested[/]")
    elif vs and safe_int(vs.get("width")) >= 3840:
        tbl.add_row("[dim]Tip[/]","[dim]4K source · [bold]Archive H.265[/] or [bold]Smart[/] preset saves most space[/]")
    console.print(Panel(tbl, title="[bold]Source File[/]", border_style="cyan", padding=(0,1)))

def show_presets_table(suggested_key: Optional[str] = None):
    tbl = Table(box=box.SIMPLE_HEAD, border_style="dim", padding=(0,1))
    tbl.add_column("#",      style="bold dim", width=3)
    tbl.add_column("Preset", width=42)
    tbl.add_column("Description")
    last_group = None
    for i, (key, p) in enumerate(PRESETS.items(), 1):
        if p.get("group") != last_group:
            tbl.add_row("","[bold dim]" + p.get("group","") + "[/]","")
            last_group = p.get("group")
        m = "  [bold cyan]<-- suggested[/]" if key == suggested_key else ""
        tbl.add_row(str(i), f"[{p['color']}]{p['emoji']}  {p['name']}[/]{m}", f"[dim]{p['desc']}[/]")
    tbl.add_row("i","[dim]Import saved preset[/]","")
    console.print(Panel(tbl, title="[bold]Presets[/]", border_style="cyan"))

def suggest_preset(info: dict) -> str:
    sz = file_size_bytes(info)
    vs = video_stream(info)
    w  = safe_int((vs or {}).get("width"))
    if is_professional(info) or sz > 500*1024*1024: return "resolve_cleanup"
    if w >= 3840: return "smart"
    return "web_1080p"

# ════════════════════════════════════════════════════════════════════════
# FILE BROWSER — supports both number input AND direct path typing
# ════════════════════════════════════════════════════════════════════════

def file_browser(start: str = "~") -> Optional[List[str]]:
    current = Path(os.path.expanduser(start)).resolve()

    while True:
        console.print()
        console.print(Rule(f"[bold cyan]File Browser[/]  [dim]{escape(str(current))}[/]"))
        try:
            raw = sorted(current.iterdir(), key=lambda p:(p.is_file(), p.name.lower()))
        except PermissionError:
            console.print("[red]  Permission denied — going up[/]")
            current = current.parent; continue

        dirs   = [e for e in raw if e.is_dir()  and not e.name.startswith(".")]
        videos = [e for e in raw if e.is_file() and e.suffix.lower() in VIDEO_EXTENSIONS]
        items: List[Tuple[Path,bool]] = []

        tbl = Table(box=box.SIMPLE, show_header=True, padding=(0,1))
        tbl.add_column("#",    style="bold dim", width=4)
        tbl.add_column("Name", width=46)
        tbl.add_column("Size", style="dim", width=10)
        tbl.add_column("Type", style="dim", width=10)

        tbl.add_row("0","[bold]..  (go up)[/]","","")
        items.append((current.parent, True))
        for d in dirs[:40]:
            n = len(items)
            try:
                cnt = sum(1 for x in d.iterdir() if x.is_file() and x.suffix.lower() in VIDEO_EXTENSIONS)
                info_s = f"{cnt} video{'s' if cnt!=1 else ''}" if cnt else ""
            except: info_s = ""
            tbl.add_row(str(n), f"[yellow]D  {escape(d.name)}[/]", "", info_s)
            items.append((d, True))
        if not videos:
            tbl.add_row("","[dim]  -- no video files here --[/]","","")
        for v in videos:
            n = len(items)
            tbl.add_row(str(n), f"[green]V  {escape(v.name)}[/]", human_size(v.stat().st_size), v.suffix.upper().lstrip("."))
            items.append((v, False))

        console.print(tbl)
        console.print()
        console.print("[dim]  #: select  |  /path or ~/path: jump to dir/file  |  a: all videos  |  r: recursive  |  q: cancel[/]")

        raw_input = Prompt.ask("[bold cyan]  >[/]").strip()
        choice    = raw_input.lower()

        if choice == "q": return None

        # ── Direct path input ──────────────────────────────────────────
        # Detect if input looks like a path (starts with / ~ . or contains /)
        if (raw_input.startswith(("/","~","./","../")) or
            (os.sep in raw_input) or
            (len(raw_input) > 2 and raw_input[1] == ":")):  # Windows C:\
            expanded = Path(os.path.expanduser(raw_input)).resolve()
            if expanded.is_dir():
                current = expanded; continue
            elif expanded.is_file():
                if expanded.suffix.lower() in VIDEO_EXTENSIONS:
                    return [str(expanded)]
                else:
                    console.print(f"  [yellow]Not a recognized video file: {expanded.suffix}[/]")
                    continue
            else:
                # Try as search/partial path
                console.print(f"  [red]Path not found: {expanded}[/]")
                continue

        # ── Commands ───────────────────────────────────────────────────
        if choice == "a":
            if videos:
                console.print(f"[green]  {len(videos)} file(s) selected[/]")
                return [str(v) for v in videos]
            console.print("[yellow]  No video files here.[/]"); continue

        if choice == "r":
            vids = [str(f) for f in sorted(current.rglob("*"))
                    if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS]
            if vids:
                console.print(f"[green]  {len(vids)} file(s) found recursively[/]")
                return vids
            console.print("[yellow]  No video files found recursively.[/]"); continue

        # ── Number input ───────────────────────────────────────────────
        try: idx = int(raw_input)
        except ValueError:
            # Partial name search
            matches = [v for v in videos if raw_input.lower() in v.name.lower()]
            if len(matches) == 1:
                return [str(matches[0])]
            elif len(matches) > 1:
                console.print(f"  [yellow]{len(matches)} matches — be more specific or use number[/]")
                for m in matches[:5]: console.print(f"  [dim]{m.name}[/]")
            else:
                console.print(f"  [red]No match for '{escape(raw_input)}'[/]")
            continue

        if idx < 0 or idx >= len(items):
            console.print(f"[red]  Out of range (0-{len(items)-1}).[/]"); continue
        path, is_dir = items[idx]
        if is_dir: current = path.resolve()
        else: return [str(path)]

# ════════════════════════════════════════════════════════════════════════
# RESOLUTION PICKER
# ════════════════════════════════════════════════════════════════════════

def pick_resolution(src_w=None, src_h=None, recommended=None, default_res=None) -> Optional[Tuple[int,int]]:
    console.print()
    console.print("[bold cyan]Resolution  (downscale only — never upscales)[/]")
    tbl = Table(box=box.SIMPLE, padding=(0,1), show_header=False)
    tbl.add_column("#", style="bold dim", width=4)
    tbl.add_column("Resolution")
    tbl.add_column("Note", style="dim")
    for i,(w,h,label) in enumerate(RESOLUTIONS):
        notes = []
        if default_res and (w,h) == default_res:           notes.append("[dim]preset default[/]")
        if recommended  and (w,h) == recommended:          notes.append("[bold cyan]<-- recommended for this target[/]")
        if w and src_w and src_h and (w > src_w or h > src_h): notes.append("(larger than source)")
        tbl.add_row(str(i), label, "  ".join(notes) if notes else "")
    tbl.add_row(str(len(RESOLUTIONS)), "Custom (enter width x height)", "")
    console.print(tbl)

    default_idx = 0
    if recommended:
        for i,(w,h,_) in enumerate(RESOLUTIONS):
            if (w,h) == recommended: default_idx = i; break
    elif default_res:
        for i,(w,h,_) in enumerate(RESOLUTIONS):
            if (w,h) == default_res: default_idx = i; break

    choices = [str(i) for i in range(len(RESOLUTIONS)+1)]
    c = Prompt.ask("Choice", choices=choices, default=str(default_idx))
    idx = int(c)
    if idx == 0: return None
    if idx < len(RESOLUTIONS):
        w,h,_ = RESOLUTIONS[idx]; return (w,h) if w else None
    w = int(Prompt.ask("  Width (px)")); h = int(Prompt.ask("  Height (px)"))
    return ((w//2)*2, (h//2)*2)

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
    console.print(Rule("[bold]Custom Configuration[/]"))

    # Codec
    console.print("\n[bold cyan]Video Codec[/]")
    codec_opts = [
        ("libx264","H.264 — widest compatibility"),
        ("libx265","H.265 — ~40% smaller, modern devices"),
        ("copy","Copy video stream (instant, recode audio only)"),
        ("libaom-av1","AV1 — next-gen, very slow"),
        ("libvpx-vp9","VP9 — open source, good quality"),
    ]
    hw = detect_hw_encoders()
    all_codecs = codec_opts + [(e,f"[HW] {l}") for e,l in hw]
    tbl = Table(box=box.SIMPLE,padding=(0,1),show_header=False)
    tbl.add_column("#",style="bold dim",width=3); tbl.add_column("Codec")
    for i,(e,l) in enumerate(all_codecs,1): tbl.add_row(str(i),l)
    console.print(tbl)
    c = Prompt.ask("Codec", choices=[str(i) for i in range(1,len(all_codecs)+1)], default="1")
    preset["codec"] = all_codecs[int(c)-1][0]

    if preset["codec"] != "copy":
        # Quality
        console.print("\n[bold cyan]Quality Mode[/]")
        console.print("  [cyan]1[/]  CRF  (constant quality, recommended)")
        console.print("  [cyan]2[/]  Target file size MB  (two-pass, precise)")
        console.print("  [cyan]3[/]  Target % of original  (two-pass)")
        qm = Prompt.ask("Mode", choices=["1","2","3"], default="1")
        if qm == "1":
            console.print("  [dim]0=lossless · 15=excellent · 18=high · 23=default · 28=compact · 33=tiny · 51=worst[/]")
            preset["crf"] = int(Prompt.ask("CRF", default="23"))
        elif qm == "2":
            preset["target_mb"] = float(Prompt.ask("Target MB", default="100"))
            preset["two_pass"]  = True
            console.print(f"  [dim]Actual target = {preset['target_mb']*BITRATE_SAFETY:.0f} MB (96% safety margin = always under)[/]")
        else:
            pct = float(Prompt.ask("Keep what % of original (e.g. 30)", default="30"))
            preset["_pct"]     = pct/100.0
            preset["two_pass"] = True

        # Speed
        hw_names = {"nvenc","vaapi","qsv","videotoolbox","amf"}
        if not any(h in preset["codec"] for h in hw_names):
            console.print("\n[bold cyan]Encode Speed[/]")
            speed_map = {"1":"ultrafast","2":"superfast","3":"veryfast","4":"faster",
                         "5":"fast","6":"medium","7":"slow","8":"slower","9":"veryslow"}
            for k,v in speed_map.items(): console.print(f"  [cyan]{k}[/]  {v}")
            sp = Prompt.ask("Speed", choices=list(speed_map.keys()), default="7")
            preset["speed"] = speed_map[sp]

        # Resolution with recommendation
        vs    = video_stream(info) if info else None
        src_w = safe_int((vs or {}).get("width"))  if vs else None
        src_h = safe_int((vs or {}).get("height")) if vs else None
        rec   = None
        if preset.get("target_mb") and src_w and src_h:
            dur = file_duration(info) if info else 0
            rec, expl = recommend_resolution_for_target(
                preset["target_mb"], dur, preset.get("audio_kbps",128), src_w, src_h)
            console.print(f"\n  [dim]Smart recommendation: {expl}[/]")
        preset["max_res"] = pick_resolution(src_w, src_h, recommended=rec)

        # Filters
        console.print("\n[bold cyan]Optional Filters[/]")
        if Confirm.ask("  Deinterlace (interlaced source)?", default=False):
            preset["_deinterlace"] = True
        if Confirm.ask("  Noise reduction (hqdn3d)?", default=False):
            preset["_denoise"] = True
        if not preset.get("two_pass"):
            if Confirm.ask("  Force two-pass (better bitrate accuracy)?", default=False):
                preset["two_pass"] = True

    # Audio
    console.print("\n[bold cyan]Audio Codec[/]")
    audio_opts = [
        ("aac","AAC — best compatibility"),("libopus","Opus — efficient, modern"),
        ("libmp3lame","MP3 — universal"),("eac3","E-AC3 (Dolby Digital Plus)"),
        ("flac","FLAC — lossless"),("copy","Copy audio unchanged"),
    ]
    tbl2 = Table(box=box.SIMPLE,padding=(0,1),show_header=False)
    tbl2.add_column("#",style="bold dim",width=3); tbl2.add_column("Codec")
    for i,(e,l) in enumerate(audio_opts,1): tbl2.add_row(str(i),l)
    console.print(tbl2)
    ac = Prompt.ask("Audio", choices=[str(i) for i in range(1,len(audio_opts)+1)], default="1")
    preset["audio_codec"] = audio_opts[int(ac)-1][0]
    if preset["audio_codec"] not in ("copy","flac"):
        preset["audio_kbps"] = int(Prompt.ask("Audio bitrate kb/s", default="128"))

    if info and len(all_audio_streams(info)) > 1:
        console.print(f"\n  [yellow]! {len(all_audio_streams(info))} audio tracks detected.[/]")
        if Confirm.ask("  Include all audio tracks?", default=True):
            preset["_all_audio"] = True

    # Export option
    if Confirm.ask("\n  Save this preset for future use?", default=False):
        name = Prompt.ask("  Preset name").strip()
        if name: export_preset(preset, name)

    return preset

# ════════════════════════════════════════════════════════════════════════
# CONFIGURE PRESET
# ════════════════════════════════════════════════════════════════════════

def configure_preset(key: str, preset: dict, info: Optional[dict]) -> dict:
    preset = dict(preset)

    if key == "smart":
        if info:
            console.print("\n  [dim]Analyzing video …[/]")
            preset = compute_smart_preset(info)
        else:
            console.print("  [yellow]Cannot analyze — no file info. Using defaults.[/]")
            preset["crf"]   = 23
            preset["speed"] = "slow"

    elif key == "target_mb":
        console.print()
        console.print(Panel(
            "[dim]Two-pass encoding with 96% safety margin — output always stays UNDER your target.\n"
            "WhatsApp video (with preview): [bold]100 MB[/]  |  Telegram: [bold]2 GB[/]\n"
            "Guide: 50 MB ~ 3-5 min 720p  |  100 MB ~ 5-10 min 720p[/]",
            border_style="dim",title="[dim]Info[/]",
        ))
        target = float(Prompt.ask("Target file size (MB)", default="100"))
        preset["target_mb"] = target
        actual = target * BITRATE_SAFETY
        console.print(f"  [dim]Actual bitrate target: {actual:.0f} MB ({BITRATE_SAFETY*100:.0f}% safety margin)[/]")
        # Smart resolution recommendation
        vs    = video_stream(info) if info else None
        src_w = safe_int((vs or {}).get("width",1920))  if vs else 1920
        src_h = safe_int((vs or {}).get("height",1080)) if vs else 1080
        dur   = file_duration(info) if info else 0
        rec, expl = recommend_resolution_for_target(target, dur, preset.get("audio_kbps",128), src_w, src_h)
        console.print(f"  [dim]Smart recommendation: {expl}[/]")
        preset["max_res"] = pick_resolution(src_w, src_h, recommended=rec)

    elif key == "target_percent":
        sz = file_size_bytes(info) if info else 0
        console.print()
        if sz > 0:
            console.print(f"  Source: [bold]{sz/1024/1024:.1f} MB[/]")
            console.print("  [dim]10 = tiny  |  30 = aggressively smaller  |  50 = half  |  80 = subtle[/]")
        pct = float(Prompt.ask("Keep what % of original size?", default="30"))
        preset["_pct"] = pct/100.0
        vs    = video_stream(info) if info else None
        src_w = safe_int((vs or {}).get("width",1920))  if vs else 1920
        src_h = safe_int((vs or {}).get("height",1080)) if vs else 1080
        if sz > 0:
            est_target = sz/1024/1024 * pct/100.0
            dur = file_duration(info) if info else 0
            rec, expl = recommend_resolution_for_target(est_target, dur, preset.get("audio_kbps",128), src_w, src_h)
            console.print(f"  [dim]Smart recommendation: {expl}[/]")
            preset["max_res"] = pick_resolution(src_w, src_h, recommended=rec)

    elif key == "whatsapp":
        console.print()
        console.print("  [dim]WhatsApp video (with preview) limit: [bold]100 MB[/], [bold]720p[/] max.\n"
                      "  As [bold]document[/]: up to 2 GB, no preview.[/]")
        as_doc = Confirm.ask("  Send as document (up to 2 GB, no preview)?", default=False)
        if as_doc:
            preset["target_mb"] = None; preset["max_res"] = None
            preset["crf"] = 20; preset["two_pass"] = False
        else:
            target = float(Prompt.ask("  Target MB (default 95)", default="95"))
            preset["target_mb"] = target
            console.print(f"  [dim]Safety margin applied: actual target ~{target*BITRATE_SAFETY:.0f} MB[/]")

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
    filters = []
    if preset.get("_deinterlace"): filters.append("yadif=mode=1")
    if preset.get("_denoise"):     filters.append("hqdn3d=4:3:6:4.5")
    max_res = preset.get("max_res")
    if max_res and src_w and src_h:
        sf = scale_vf(src_w, src_h, max_res)
        if sf: filters.append(sf)
    # Always ensure even dimensions
    if not any("scale=" in f for f in filters):
        filters.append("scale=trunc(iw/2)*2:trunc(ih/2)*2")
    return filters

def build_cmd(input_path, output_path, preset, src_w, src_h,
              video_kbps=None, pass_num=0, passlog=None) -> List[str]:
    cmd = ["ffmpeg","-hide_banner","-y","-i",input_path]
    co  = preset.get("codec") or "libx264"

    if co == "copy":
        ac = preset.get("audio_codec") or "aac"
        ab = preset.get("audio_kbps") or 192
        am = ["-map","0:v","-map","0:a"] if preset.get("_all_audio") else ["-map","0:v","-map","0:a?"]
        cmd += am + ["-c:v","copy"]
        cmd += ["-c:a","copy"] if ac=="copy" else ["-c:a",ac,"-b:a",f"{ab}k"]
        cmd += ["-movflags","+faststart",output_path]
        return cmd

    vf_list = build_vf_list(preset, src_w, src_h)
    if vf_list: cmd += ["-vf",",".join(vf_list)]
    am = ["-map","0:v","-map","0:a"] if preset.get("_all_audio") else ["-map","0:v","-map","0:a?"]
    cmd += am

    if co == "libx264":
        cmd += ["-c:v","libx264","-profile:v","high","-pix_fmt","yuv420p"]
    elif co == "libx265":
        cmd += ["-c:v","libx265","-pix_fmt","yuv420p","-tag:v","hvc1"]
    else:
        cmd += ["-c:v",co,"-pix_fmt","yuv420p"]

    if video_kbps:
        maxr = int(video_kbps*1.3); bufs = int(video_kbps*2.0)
        cmd += ["-b:v",f"{video_kbps}k","-maxrate",f"{maxr}k","-bufsize",f"{bufs}k"]
    elif preset.get("crf") is not None:
        cmd += ["-crf",str(preset["crf"])]

    sp = preset.get("speed")
    hw_names = {"nvenc","vaapi","qsv","videotoolbox","amf"}
    if sp and not any(h in co for h in hw_names): cmd += ["-preset",sp]

    if pass_num == 1:
        cmd += ["-pass","1","-passlogfile",passlog,"-an","-f","mp4","/dev/null"]
        return cmd
    elif pass_num == 2:
        cmd += ["-pass","2","-passlogfile",passlog]

    ac = preset.get("audio_codec") or "aac"
    ab = preset.get("audio_kbps") or 128
    if ac == "copy":   cmd += ["-c:a","copy"]
    elif ac == "flac": cmd += ["-c:a","flac"]
    else:              cmd += ["-c:a",ac,"-b:a",f"{ab}k"]
    cmd += ["-movflags","+faststart",output_path]
    return cmd

# ════════════════════════════════════════════════════════════════════════
# PROGRESS
# ════════════════════════════════════════════════════════════════════════

def run_with_progress(cmd: List[str], duration_s: float, label: str = "Encoding") -> bool:
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description:<24}"),
        BarColumn(bar_width=36,complete_style="cyan",finished_style="green"),
        TaskProgressColumn(),
        TextColumn("[dim]{task.fields[eta]:<14}"),
        TextColumn("[dim]{task.fields[speed]}"),
        console=console,transient=False,
    ) as prog:
        task = prog.add_task(label, total=100, eta="", speed="")
        try:
            proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True)
        except FileNotFoundError:
            console.print("[red]  ffmpeg not found![/]"); return False

        for line in proc.stderr:
            t = parse_progress_time(line)
            if t and duration_s > 0:
                pct  = min(99.9, t/duration_s*100)
                sm   = re.search(r"speed=\s*([\d.]+)x", line)
                spd  = float(sm.group(1)) if sm else 0.0
                sp_s = f"{spd:.1f}x" if spd > 0 else ""
                rem  = (duration_s-t)/spd if spd > 0.01 else 0
                eta  = f"ETA {human_dur(rem)}" if rem > 2 else ""
                prog.update(task, completed=pct, speed=sp_s, eta=eta)

        proc.wait()
        if proc.returncode == 0:
            prog.update(task, completed=100, eta="", speed="done")
            return True
        prog.stop()
        console.print(f"[red]  FFmpeg exited {proc.returncode}[/]")
        return False

# ════════════════════════════════════════════════════════════════════════
# ENCODE — with HW fallback and post-encode size verification
# ════════════════════════════════════════════════════════════════════════

def encode_file(input_path, output_path, preset, info, idx=0, total=1) -> bool:
    duration = file_duration(info)
    vs       = video_stream(info)
    src_w    = safe_int((vs or {}).get("width"))  if vs else None
    src_h    = safe_int((vs or {}).get("height")) if vs else None
    label_p  = f"[{idx}/{total}] " if total > 1 else ""

    # Hardware encoder fallback
    co = preset.get("codec") or "libx264"
    hw_names = {"nvenc","vaapi","qsv","videotoolbox","amf"}
    if any(h in co for h in hw_names):
        preset = dict(preset)
        preset["codec"] = hw_encoder_fallback(co, input_path)

    # Percent target
    if preset.get("_pct") and file_size_bytes(info) > 0 and duration > 0:
        preset = dict(preset)
        preset["target_mb"] = file_size_bytes(info)/1024/1024 * preset["_pct"]
        console.print(f"  [dim]Target: {preset['target_mb']:.1f} MB ({preset['_pct']*100:.0f}% of original)[/]")

    # Copy
    if preset.get("codec") == "copy":
        cmd = build_cmd(input_path, output_path, preset, src_w, src_h)
        return run_with_progress(cmd, duration, f"{label_p}Remuxing")

    # Two-pass
    if preset.get("target_mb") and duration > 0:
        akbps   = preset.get("audio_kbps") or 128
        vkbps   = target_video_kbps(preset["target_mb"], duration, akbps, BITRATE_SAFETY)
        tmpdir  = tempfile.mkdtemp(prefix="fftoolbox_")
        passlog = os.path.join(tmpdir,"ff2pass")

        safe_target = preset["target_mb"] * BITRATE_SAFETY
        est_mb = (vkbps+akbps)*1000*duration/(8*1024*1024)
        console.print(
            f"  [dim]Two-pass · user target {preset['target_mb']:.0f} MB · "
            f"safety target {safe_target:.0f} MB · video {vkbps} kb/s · est. {est_mb:.1f} MB[/]"
        )

        cmd1 = build_cmd(input_path, output_path, preset, src_w, src_h, vkbps, 1, passlog)
        ok = run_with_progress(cmd1, duration, f"{label_p}Pass 1/2")
        if ok:
            cmd2 = build_cmd(input_path, output_path, preset, src_w, src_h, vkbps, 2, passlog)
            ok = run_with_progress(cmd2, duration, f"{label_p}Pass 2/2")
        try: shutil.rmtree(tmpdir)
        except: pass

        # Post-encode verification
        if ok and os.path.exists(output_path):
            actual_mb = os.path.getsize(output_path) / 1024 / 1024
            user_target = preset["target_mb"]
            if actual_mb > user_target:
                over = actual_mb - user_target
                console.print(
                    f"  [yellow]! Output {actual_mb:.1f} MB is {over:.1f} MB over target {user_target:.0f} MB.[/]\n"
                    f"  [dim]Rare edge case (B-frames, container). Re-encoding with tighter budget …[/]"
                )
                # Re-encode with tighter budget (90% safety)
                vkbps2   = target_video_kbps(user_target, duration, akbps, 0.90)
                tmpdir2  = tempfile.mkdtemp(prefix="fftoolbox_")
                passlog2 = os.path.join(tmpdir2,"ff2pass_retry")
                cmd1r = build_cmd(input_path, output_path, preset, src_w, src_h, vkbps2, 1, passlog2)
                ok2   = run_with_progress(cmd1r, duration, f"{label_p}Retry P1/2")
                if ok2:
                    cmd2r = build_cmd(input_path, output_path, preset, src_w, src_h, vkbps2, 2, passlog2)
                    run_with_progress(cmd2r, duration, f"{label_p}Retry P2/2")
                try: shutil.rmtree(tmpdir2)
                except: pass
        return ok

    # CRF single-pass
    cmd = build_cmd(input_path, output_path, preset, src_w, src_h)
    return run_with_progress(cmd, duration, f"{label_p}Encoding")

# ════════════════════════════════════════════════════════════════════════
# OUTPUT DIR
# ════════════════════════════════════════════════════════════════════════

def pick_output_dir(first_file: str) -> str:
    src     = Path(first_file).parent
    beside  = str(src/"fftoolbox_output")
    same    = str(src)
    desktop = os.path.expanduser("~/Desktop/fftoolbox_output")
    console.print()
    console.print("[bold cyan]Output Directory[/]")
    console.print(f"  [cyan]1[/]  Subfolder beside source  [dim]{escape(beside)}[/]")
    console.print(f"  [cyan]2[/]  Same folder as source    [dim]{escape(same)}[/]")
    console.print(f"  [cyan]3[/]  Desktop                  [dim]{escape(desktop)}[/]")
    console.print("  [cyan]4[/]  Custom path")
    c = Prompt.ask("Choice", choices=["1","2","3","4"], default="1")
    if c=="1": return beside
    if c=="2": return same
    if c=="3": return desktop
    return os.path.expanduser(Prompt.ask("Path").strip())

def size_feedback(src_sz: int, dst_path: str, preset_key: str):
    try: dst_sz = os.path.getsize(dst_path)
    except: return
    pct = (1-dst_sz/src_sz)*100 if src_sz > 0 else 0
    clr = "green" if pct > 5 else ("yellow" if pct > -5 else "red")
    direction = "smaller" if pct > 0 else "LARGER"
    console.print(
        f"  [green]OK[/]  {human_size(src_sz)} → [{clr}]{human_size(dst_sz)}[/]"
        f"  ({abs(pct):.1f}% {direction})"
    )
    dst_mb = dst_sz/1024/1024
    if preset_key == "whatsapp" and dst_mb > WHATSAPP_VIDEO_MB:
        console.print(
            f"\n  [bold yellow]! Output {dst_mb:.1f} MB — over WhatsApp's {WHATSAPP_VIDEO_MB} MB video limit.[/]\n"
            "  [dim]Use [bold]Target File Size[/] at 95 MB, or send as a document in WhatsApp (no preview, up to 2 GB).[/]"
        )
    elif dst_sz > src_sz and dst_sz-src_sz > 512*1024:
        console.print("  [yellow]! Output is larger than input — source may already be well-compressed.[/]")

# ════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════

def main():
    print_banner()

    # Background update check
    import threading
    threading.Thread(target=check_for_update, daemon=True).start()

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
        console.print("  [dim]Hardware encoders: " + ", ".join(l for _,l in hw[:3])
                      + ("[/]" if len(hw)<=3 else f" +{len(hw)-3} more[/]"))
        console.print()

    # ── STEP 1: Files ────────────────────────────────────────────────────
    console.print(Rule("[bold]Step 1 · Select File(s)[/]"))
    console.print()
    console.print("  [cyan]1[/]  Browse interactively  [dim](type numbers OR paste paths directly)[/]")
    console.print("  [cyan]2[/]  Paste file or directory path")
    console.print("  [cyan]3[/]  Entire directory  (batch)")
    sel = Prompt.ask("How", choices=["1","2","3"], default="1")
    files: List[str] = []

    if sel == "1":
        result = file_browser(os.path.expanduser("~"))
        if not result: console.print("[yellow]  Cancelled.[/]"); return
        files = result
    elif sel == "2":
        raw = os.path.expanduser(Prompt.ask("Path").strip())
        p = Path(raw)
        if p.is_file(): files = [str(p)]
        elif p.is_dir():
            files = sorted(str(f) for f in p.iterdir()
                          if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS)
        else: console.print(f"[red]  Not found: {raw}[/]"); return
    elif sel == "3":
        raw = os.path.expanduser(Prompt.ask("Directory path").strip())
        p = Path(raw)
        if not p.is_dir(): console.print(f"[red]  Not a directory.[/]"); return
        recursive = Confirm.ask("  Include subdirectories?", default=False)
        glob = p.rglob("*") if recursive else p.iterdir()
        files = sorted(str(f) for f in glob if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS)

    if not files: console.print("[red]  No video files found.[/]"); return
    files = sorted(set(files))
    console.print(f"\n  [green]OK[/]  [bold]{len(files)} file(s) selected[/]")
    for f in files[:5]: console.print(f"  [dim]{escape(f)}[/]")
    if len(files) > 5: console.print(f"  [dim]… and {len(files)-5} more[/]")

    console.print()
    first_info = run_ffprobe(files[0])
    if first_info: print_file_info(first_info, files[0])
    else: console.print("[yellow]  Could not read media info.[/]")

    # ── STEP 2: Preset ───────────────────────────────────────────────────
    console.print()
    console.print(Rule("[bold]Step 2 · Choose Preset[/]"))
    console.print()
    suggested = suggest_preset(first_info) if first_info else "web_1080p"
    show_presets_table(suggested)

    preset_keys  = list(PRESETS.keys())
    suggested_no = str(preset_keys.index(suggested)+1)
    valid_nos    = [str(i) for i in range(1,len(preset_keys)+1)]

    raw_choice = Prompt.ask("Preset number (or 'i' to import)", default=suggested_no).strip().lower()

    if raw_choice == "i":
        imported = import_preset_menu()
        if not imported: console.print("[yellow]  Import cancelled.[/]"); return
        selected_key = "_imported"
        preset       = imported
    else:
        if raw_choice not in valid_nos:
            console.print("[red]  Invalid choice.[/]"); return
        selected_key = preset_keys[int(raw_choice)-1]
        preset       = dict(PRESETS[selected_key])
        tip = preset.get("tip","")
        if tip: console.print(f"\n  [dim]{tip}[/]")
        preset = configure_preset(selected_key, preset, first_info)

    color = preset.get("color","cyan")
    console.print(f"\n  [green]OK[/]  [{color}]{preset.get('emoji','')} {preset.get('name','Custom')}[/]")

    # Preview encode option
    console.print()
    if len(files) == 1 and first_info and preset.get("codec") != "copy":
        if Confirm.ask("  Run a 5-second preview encode first?", default=False):
            if not run_preview_encode(files[0], preset, first_info):
                console.print("[yellow]  Cancelled after preview.[/]"); return

    # ── STEP 3: Output dir ───────────────────────────────────────────────
    output_dir = pick_output_dir(files[0])
    try: os.makedirs(output_dir, exist_ok=True)
    except OSError as e: console.print(f"[red]  Cannot create output dir: {e}[/]"); return
    console.print(f"  [green]OK[/]  Output: [dim]{escape(output_dir)}[/]")

    # ── STEP 4: Plan ─────────────────────────────────────────────────────
    console.print()
    console.print(Rule("[bold]Encode Plan[/]"))
    plan_tbl = Table(box=box.SIMPLE, padding=(0,1))
    plan_tbl.add_column("File",     max_width=34, overflow="fold")
    plan_tbl.add_column("Size",     style="dim", width=10)
    plan_tbl.add_column("Duration", style="dim", width=10)
    plan_tbl.add_column("Res",      style="dim", width=12)
    plan_tbl.add_column("Output",   max_width=28, overflow="fold")
    infos: Dict[str,Optional[dict]] = {files[0]: first_info}
    total_src = 0
    for f in files:
        fi = infos.get(f) or run_ffprobe(f); infos[f] = fi
        out = f"{Path(f).stem}_{selected_key if selected_key != '_imported' else 'custom'}.mp4"
        if fi:
            sz=file_size_bytes(fi); dur=file_duration(fi)
            vs=video_stream(fi); w=(vs or {}).get("width","?"); h=(vs or {}).get("height","?")
            total_src += sz
            plan_tbl.add_row(Path(f).name, human_size(sz), human_dur(dur), f"{w}x{h}", out)
        else:
            plan_tbl.add_row(Path(f).name,"?","?","?",out)
    console.print(plan_tbl)
    if total_src > 0: console.print(f"  [dim]Total input: {human_size(total_src)}[/]")

    console.print()
    if not Confirm.ask("[bold]Start encoding now?[/]", default=True):
        console.print("[yellow]  Cancelled.[/]"); return

    # ── STEP 5: Encode ───────────────────────────────────────────────────
    console.print()
    console.print(Rule("[bold cyan]Encoding[/]"))
    success, failed = 0, 0
    results: List[Tuple[str,str,int,int]] = []
    sfx = selected_key if selected_key != "_imported" else "custom"

    for i, fpath in enumerate(files, 1):
        console.print()
        console.print(f"  [bold][{i}/{len(files)}][/]  {escape(Path(fpath).name)}")
        fi = infos.get(fpath) or run_ffprobe(fpath)
        if not fi:
            console.print("  [red]  Could not read — skipping[/]"); failed += 1; continue

        file_preset = dict(preset)
        if preset.get("_pct") and file_size_bytes(fi) > 0:
            file_preset["target_mb"] = file_size_bytes(fi)/1024/1024 * preset["_pct"]

        out_name = f"{Path(fpath).stem}_{sfx}.mp4"
        out_path = os.path.join(output_dir, out_name)

        # Collision handling
        if os.path.exists(out_path):
            out_path = handle_collision(out_path)
            if out_path is None:
                console.print("  [dim]  Skipped.[/]"); continue

        try:
            ok = encode_file(fpath, out_path, file_preset, fi, i, len(files))
        except Exception as exc:
            console.print(f"  [red]  Error: {exc}[/]")
            if os.environ.get("FFTOOLBOX_DEBUG"):
                console.print(f"  [dim]{traceback.format_exc()}[/]")
            ok = False

        if ok and os.path.exists(out_path):
            src_sz = file_size_bytes(fi)
            dst_sz = os.path.getsize(out_path)
            size_feedback(src_sz, out_path, selected_key)
            console.print(f"  [dim]{escape(out_path)}[/]")
            success += 1
            results.append((fpath, out_path, src_sz, dst_sz))
        else:
            failed += 1

    # ── STEP 6: Summary ──────────────────────────────────────────────────
    console.print()
    console.print(Rule("[bold]Summary[/]"))
    parts = [f"[green]{success} succeeded[/]"]
    if failed: parts.append(f"[red]{failed} failed[/]")
    console.print("  " + "  |  ".join(parts))
    if results:
        tin  = sum(r[2] for r in results)
        tout = sum(r[3] for r in results)
        saved = tin-tout
        pct = (saved/tin*100) if tin > 0 else 0
        clr = "green" if saved > 0 else "yellow"
        console.print(
            f"  Total  {human_size(tin)} → [{clr}]{human_size(tout)}[/]"
            + (f"  [green](saved {human_size(saved)}, {pct:.1f}%)[/]" if saved > 0
               else f"  [yellow](+{human_size(-saved)} larger)[/]")
        )
    console.print(f"\n  [bold]Output:[/] [cyan]{escape(output_dir)}[/]")
    console.print()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n\n  [yellow]Aborted.[/]")
        sys.exit(1)
