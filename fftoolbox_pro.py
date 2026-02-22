#!/usr/bin/env python3
"""
fftoolbox_pro.py — Smart Video Converter · v1.0
================================================
Run directly:  python3 fftoolbox_pro.py
As system cmd: sudo cp fftoolbox_pro.py /usr/local/bin/fftoolbox
               sudo chmod +x /usr/local/bin/fftoolbox
               fftoolbox

Requirements:
  · Python 3.8+
  · ffmpeg + ffprobe in PATH (sudo apt install ffmpeg)
  · pip install rich  (auto-installed on first run)

License: MIT · https://github.com/yourusername/fftoolbox
"""

import sys, os, re, json, math, time, shutil, tempfile, subprocess, traceback
from pathlib import Path
from datetime import timedelta
from typing import Optional, List, Tuple, Dict, Any

# ── auto-install rich ────────────────────────────────────────────────────────
def _ensure_rich():
    try:
        import rich
    except ImportError:
        print("Installing 'rich' for beautiful UI …")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "rich", "--quiet"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            print("Done.\n")
        except Exception as e:
            print(f"ERROR: pip install rich failed: {e}\nPlease run: pip install rich")
            sys.exit(1)

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

APP_VERSION = "1.0"
APP_NAME    = "fftoolbox"

VIDEO_EXTENSIONS = {
    ".mp4",".mov",".mkv",".m4v",".avi",".wmv",".flv",".webm",
    ".mxf",".ts",".mts",".m2ts",".mpg",".mpeg",".3gp",".ogv",".dv",".vob",
}
PROFESSIONAL_CODECS = {
    "prores","prores_ks","dnxhd","dnxhr","mjpeg","v210",
    "r10k","r210","cineform","cfhd","huffyuv","ffv1","utvideo",
}

WHATSAPP_VIDEO_MB = 100

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
    "whatsapp": {
        "group":"Sharing","name":"WhatsApp  (< 100 MB, 720p max)","emoji":"📱",
        "desc":"Two-pass to hit < 100 MB · 720p · H.264 · AAC · universal compat",
        "codec":"libx264","crf":None,"speed":"slow","audio_codec":"aac","audio_kbps":96,
        "max_res":(1280,720),"target_mb":95,"two_pass":True,"color":"green",
        "tip":"WhatsApp shows video previews up to 100 MB. Two-pass hits the target precisely.",
    },
    "telegram": {
        "group":"Sharing","name":"Telegram  (1080p, great quality)","emoji":"✈️",
        "desc":"1080p max · H.264 CRF 22 · AAC 192 · Telegram supports up to 2 GB",
        "codec":"libx264","crf":22,"speed":"slow","audio_codec":"aac","audio_kbps":192,
        "max_res":(1920,1080),"target_mb":None,"two_pass":False,"color":"bright_blue",
        "tip":"Telegram keeps quality intact and supports files up to 2 GB.",
    },
    "resolve_cleanup": {
        "group":"Professional","name":"DaVinci Resolve Cleanup","emoji":"🎬",
        "desc":"ProRes / DNxHR  ->  H.264 · CRF 18 · near-lossless quality",
        "codec":"libx264","crf":18,"speed":"slow","audio_codec":"aac","audio_kbps":192,
        "max_res":None,"target_mb":None,"two_pass":False,"color":"cyan",
        "tip":"CRF 18 = near-lossless. Shrinks 10 GB Resolve exports to ~300–800 MB.",
    },
    "archive_h265": {
        "group":"Professional","name":"Archive  (H.265 / HEVC)","emoji":"🗄️",
        "desc":"CRF 18 · ~40 % smaller than H.264 · long-term storage · Apple HVC1 tag",
        "codec":"libx265","crf":18,"speed":"slow","audio_codec":"aac","audio_kbps":192,
        "max_res":None,"target_mb":None,"two_pass":False,"color":"blue",
        "tip":"Best long-term archive format. Compatible with modern devices.",
    },
    "web_1080p": {
        "group":"Web","name":"Web / Social Media  (1080p)","emoji":"🌐",
        "desc":"H.264 · CRF 23 · 1080p max · fast-start · YouTube / Vimeo / Instagram",
        "codec":"libx264","crf":23,"speed":"slow","audio_codec":"aac","audio_kbps":128,
        "max_res":(1920,1080),"target_mb":None,"two_pass":False,"color":"yellow",
        "tip":"Safe choice for any online platform. Good quality, reasonable size.",
    },
    "compress_light": {
        "group":"Compression","name":"Compress Light  (~25 % smaller)","emoji":"🟢",
        "desc":"CRF 20 · barely noticeable quality loss · ~25 % size reduction",
        "codec":"libx264","crf":20,"speed":"medium","audio_codec":"aac","audio_kbps":192,
        "max_res":None,"target_mb":None,"two_pass":False,"color":"bright_green",
        "tip":"Barely any quality loss. Great when you need a slightly smaller file.",
    },
    "compress_medium": {
        "group":"Compression","name":"Compress Medium  (~50 % smaller)","emoji":"🟡",
        "desc":"CRF 26 · noticeable but acceptable · ~50 % size reduction",
        "codec":"libx264","crf":26,"speed":"medium","audio_codec":"aac","audio_kbps":128,
        "max_res":None,"target_mb":None,"two_pass":False,"color":"yellow",
        "tip":"Good balance. Clearly smaller file, still very watchable.",
    },
    "compress_heavy": {
        "group":"Compression","name":"Compress Heavy  (~75 % smaller)","emoji":"🔴",
        "desc":"CRF 32 · clear quality loss · 720p max · ~75 % smaller",
        "codec":"libx264","crf":32,"speed":"fast","audio_codec":"aac","audio_kbps":64,
        "max_res":(1280,720),"target_mb":None,"two_pass":False,"color":"red",
        "tip":"Maximum compression. Pixelation may be visible. For quick sharing only.",
    },
    "target_mb": {
        "group":"Exact Control","name":"Target Exact File Size  (MB)","emoji":"📐",
        "desc":"Enter target MB  ->  two-pass bitrate encoding hits the mark",
        "codec":"libx264","crf":None,"speed":"slow","audio_codec":"aac","audio_kbps":128,
        "max_res":None,"target_mb":None,"two_pass":True,"color":"magenta",
        "tip":"Most precise control. Slower because of two passes.",
    },
    "target_percent": {
        "group":"Exact Control","name":"Target % Compression","emoji":"📊",
        "desc":"Enter what % of original size you want  ->  auto bitrate + two-pass",
        "codec":"libx264","crf":None,"speed":"slow","audio_codec":"aac","audio_kbps":128,
        "max_res":None,"target_mb":None,"two_pass":True,"color":"magenta",
        "tip":"E.g. 30  ->  output is ~30 % of original size.",
    },
    "quick": {
        "group":"Utility","name":"Quick Convert  (fast encode)","emoji":"⚡",
        "desc":"H.264 · CRF 23 · medium speed · any resolution",
        "codec":"libx264","crf":23,"speed":"medium","audio_codec":"aac","audio_kbps":128,
        "max_res":None,"target_mb":None,"two_pass":False,"color":"bright_yellow",
        "tip":"Fast encode. Good quality. Ideal for batch jobs.",
    },
    "fix_audio": {
        "group":"Utility","name":"Fix Audio  (copy video)","emoji":"🔊",
        "desc":"Video stream copied unchanged · audio  ->  AAC 192 kb/s · instant",
        "codec":"copy","crf":None,"speed":None,"audio_codec":"aac","audio_kbps":192,
        "max_res":None,"target_mb":None,"two_pass":False,"color":"white",
        "tip":"Almost instant — only audio is processed. Fixes codec compat issues.",
    },
    "custom": {
        "group":"Custom","name":"Custom — full manual control","emoji":"⚙️",
        "desc":"Configure codec, CRF, speed, resolution, audio, hardware encoders",
        "codec":None,"crf":None,"speed":None,"audio_codec":None,"audio_kbps":None,
        "max_res":None,"target_mb":None,"two_pass":False,"color":"dim white",
        "tip":"Full control over every parameter.",
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
    except json.JSONDecodeError as e:
        console.print(f"[red]  ffprobe JSON error: {e}[/]"); return None
    except subprocess.CalledProcessError as e:
        console.print(f"[red]  ffprobe failed: {(e.stderr or '')[:200]}[/]"); return None

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

def is_professional(info: dict) -> bool:
    vs = video_stream(info)
    vc = (vs or {}).get("codec_name","").lower()
    return any(p in vc for p in PROFESSIONAL_CODECS)

def safe_int(val, default=0) -> int:
    try: return int(val)
    except: return default

def detect_hw_encoders() -> List[Tuple[str,str]]:
    candidates = [
        ("h264_nvenc","NVIDIA NVENC H.264"),("hevc_nvenc","NVIDIA NVENC H.265"),
        ("h264_vaapi","VAAPI H.264 (Intel/AMD)"),("hevc_vaapi","VAAPI H.265 (Intel/AMD)"),
        ("h264_qsv","Intel QuickSync H.264"),("hevc_qsv","Intel QuickSync H.265"),
        ("h264_amf","AMD AMF H.264"),("hevc_amf","AMD AMF H.265"),
        ("h264_videotoolbox","Apple VideoToolbox H.264"),("hevc_videotoolbox","Apple VideoToolbox H.265"),
    ]
    try:
        r = subprocess.run(["ffmpeg","-hide_banner","-encoders"],
                           stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=5)
        out = r.stdout
        return [(e,l) for e,l in candidates if e in out]
    except: return []

def scale_vf(src_w: int, src_h: int, max_res: Tuple[int,int]) -> Optional[str]:
    mw, mh = max_res
    if src_w <= mw and src_h <= mh: return None
    ratio = min(mw/src_w, mh/src_h)
    nw = (int(src_w*ratio)//2)*2
    nh = (int(src_h*ratio)//2)*2
    return f"scale={nw}:{nh}:flags=lanczos"

def target_video_kbps(target_mb: float, duration_s: float, audio_kbps: int) -> int:
    bits = target_mb * 8 * 1024 * 1024
    return max(100, int(bits/duration_s/1000 - audio_kbps))

def parse_progress_time(line: str) -> Optional[float]:
    m = re.search(r"time=(\d+):(\d+):([\d.]+)", line)
    if m: return int(m.group(1))*3600 + int(m.group(2))*60 + float(m.group(3))
    return None

# ════════════════════════════════════════════════════════════════════════
# UI
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
    as_ = audio_stream(info)
    dur = file_duration(info)
    sz  = file_size_bytes(info)
    vc  = (vs or {}).get("codec_name","?").upper()
    ac  = (as_ or {}).get("codec_name","?").upper()

    tbl = Table(box=box.ROUNDED, border_style="dim", show_header=False, padding=(0,1))
    tbl.add_column("K", style="bold cyan", width=16)
    tbl.add_column("V", style="white")
    tbl.add_row("Filename",  escape(Path(path).name))
    tbl.add_row("Size",      human_size(sz))
    tbl.add_row("Duration",  human_dur(dur))
    if vs:
        w, h = vs.get("width","?"), vs.get("height","?")
        tbl.add_row("Resolution", f"{w} x {h}")
        tbl.add_row("FPS",        fps_str(vs))
        bit = vs.get("bit_rate")
        if bit: tbl.add_row("Video bitrate", f"{int(bit)//1000} kb/s")
    vc_display = vc
    if any(p in vc.lower() for p in PROFESSIONAL_CODECS):
        vc_display = f"[bold yellow]! {vc}  (professional codec — large file expected)[/]"
    tbl.add_row("Video codec", vc_display)
    na = len(all_audio_streams(info))
    tbl.add_row("Audio codec", f"{ac}" + (f"  ({na} tracks)" if na > 1 else ""))
    if sz > 500*1024*1024:
        tbl.add_row("[yellow]Tip[/]","[yellow]Large file — [bold]DaVinci Resolve Cleanup[/] preset recommended[/]")
    elif vs and safe_int(vs.get("width")) >= 3840:
        tbl.add_row("[yellow]Tip[/]","[dim]4K source · [bold]Archive H.265[/] preset saves most space[/]")
    console.print(Panel(tbl, title="[bold]Source File[/]", border_style="cyan", padding=(0,1)))

def show_presets_table(suggested_key: Optional[str] = None):
    tbl = Table(box=box.SIMPLE_HEAD, border_style="dim", padding=(0,1))
    tbl.add_column("#",      style="bold dim", width=3)
    tbl.add_column("Preset", width=40)
    tbl.add_column("Description")
    last_group = None
    for i, (key, p) in enumerate(PRESETS.items(), 1):
        if p.get("group") != last_group:
            tbl.add_row("", f"[bold dim]── {p.get('group','')} ──[/]", "")
            last_group = p.get("group")
        m = "  [bold cyan]<-- suggested[/]" if key == suggested_key else ""
        tbl.add_row(str(i), f"[{p['color']}]{p['emoji']}  {p['name']}[/]{m}", f"[dim]{p['desc']}[/]")
    console.print(Panel(tbl, title="[bold]Presets[/]", border_style="cyan"))

def suggest_preset(info: dict) -> str:
    sz  = file_size_bytes(info)
    vs  = video_stream(info)
    w   = safe_int((vs or {}).get("width"))
    if is_professional(info) or sz > 500*1024*1024: return "resolve_cleanup"
    if w >= 3840: return "archive_h265"
    return "web_1080p"

# ════════════════════════════════════════════════════════════════════════
# FILE BROWSER
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
        tbl.add_column("Name", width=48)
        tbl.add_column("Size", style="dim", width=10)
        tbl.add_column("Type", style="dim", width=10)

        tbl.add_row("0","[bold]..  (go up)[/]","","")
        items.append((current.parent, True))
        for d in dirs[:40]:
            n = len(items)
            try:
                cnt = sum(1 for x in d.iterdir() if x.is_file() and x.suffix.lower() in VIDEO_EXTENSIONS)
                info_str = f"{cnt} video{'s' if cnt!=1 else ''}" if cnt else ""
            except: info_str = ""
            tbl.add_row(str(n), f"[yellow]D  {escape(d.name)}[/]", "", info_str)
            items.append((d, True))
        if not videos:
            tbl.add_row("","[dim]  -- no video files here --[/]","","")
        for v in videos:
            n = len(items)
            sz = v.stat().st_size
            tbl.add_row(str(n), f"[green]V  {escape(v.name)}[/]", human_size(sz), v.suffix.upper().lstrip("."))
            items.append((v, False))

        console.print(tbl)
        console.print()
        console.print("[dim]  Number: open / select  |  a: all videos here  |  r: recursive  |  p: paste path  |  q: cancel[/]")

        choice = Prompt.ask("[bold cyan]  >[/]").strip().lower()
        if choice == "q": return None
        if choice == "a":
            if videos:
                console.print(f"[green]  {len(videos)} file(s) selected[/]")
                return [str(v) for v in videos]
            console.print("[yellow]  No video files here.[/]"); continue
        if choice == "r":
            vids = [str(f) for f in sorted(current.rglob("*")) if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS]
            if vids:
                console.print(f"[green]  {len(vids)} file(s) found recursively[/]")
                return vids
            console.print("[yellow]  No video files found.[/]"); continue
        if choice == "p":
            raw_p = os.path.expanduser(Prompt.ask("  Path").strip())
            p_obj = Path(raw_p)
            if p_obj.is_dir(): current = p_obj.resolve()
            elif p_obj.is_file(): return [str(p_obj)]
            else: console.print(f"[red]  Not found: {raw_p}[/]")
            continue
        try: idx = int(choice)
        except: console.print("[red]  Enter a number.[/]"); continue
        if idx < 0 or idx >= len(items):
            console.print(f"[red]  Out of range (0-{len(items)-1}).[/]"); continue
        path, is_dir = items[idx]
        if is_dir: current = path.resolve()
        else: return [str(path)]

# ════════════════════════════════════════════════════════════════════════
# RESOLUTION PICKER
# ════════════════════════════════════════════════════════════════════════

def pick_resolution(src_w=None, src_h=None, default_res=None) -> Optional[Tuple[int,int]]:
    console.print()
    console.print("[bold cyan]Resolution  (downscale only — never upscales)[/]")
    tbl = Table(box=box.SIMPLE, padding=(0,1), show_header=False)
    tbl.add_column("#", style="bold dim", width=4)
    tbl.add_column("Resolution")
    tbl.add_column("Note", style="dim")
    for i,(w,h,label) in enumerate(RESOLUTIONS):
        note = ""
        if default_res and (w,h) == default_res: note = "[cyan]<- preset default[/]"
        if w and src_w and src_h and (w > src_w or h > src_h): note = "(larger than source - skipped)"
        tbl.add_row(str(i), label, note)
    tbl.add_row(str(len(RESOLUTIONS)), "Custom (enter width x height)", "")
    console.print(tbl)
    default_idx = 0
    if default_res:
        for i,(w,h,_) in enumerate(RESOLUTIONS):
            if (w,h)==default_res: default_idx=i; break
    choices = [str(i) for i in range(len(RESOLUTIONS)+1)]
    c = Prompt.ask("Choice", choices=choices, default=str(default_idx))
    idx = int(c)
    if idx == 0: return None
    if idx < len(RESOLUTIONS):
        w,h,_ = RESOLUTIONS[idx]
        return (w,h) if w else None
    w = int(Prompt.ask("  Width (px)"))
    h = int(Prompt.ask("  Height (px)"))
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
    tbl.add_column("#",style="bold dim",width=3)
    tbl.add_column("Codec")
    for i,(e,l) in enumerate(all_codecs,1): tbl.add_row(str(i),l)
    console.print(tbl)
    c = Prompt.ask("Codec", choices=[str(i) for i in range(1,len(all_codecs)+1)], default="1")
    preset["codec"] = all_codecs[int(c)-1][0]

    if preset["codec"] != "copy":
        # Quality
        console.print("\n[bold cyan]Quality Mode[/]")
        console.print("  [cyan]1[/]  CRF  (constant quality — recommended)")
        console.print("  [cyan]2[/]  Target file size MB  (two-pass)")
        console.print("  [cyan]3[/]  Target % of original size  (two-pass)")
        qm = Prompt.ask("Mode", choices=["1","2","3"], default="1")
        if qm == "1":
            console.print("  [dim]0=lossless · 15=near-lossless · 18=high · 23=default · 28=compact · 33=tiny · 51=worst[/]")
            preset["crf"] = int(Prompt.ask("CRF", default="23"))
        elif qm == "2":
            preset["target_mb"] = float(Prompt.ask("Target MB", default="100"))
            preset["two_pass"]  = True
        else:
            pct = float(Prompt.ask("Keep what % of original (e.g. 30)", default="30"))
            preset["_pct"]     = pct/100.0
            preset["two_pass"] = True

        # Speed
        hw_names = {"nvenc","vaapi","qsv","videotoolbox","amf"}
        if not any(h in preset["codec"] for h in hw_names):
            console.print("\n[bold cyan]Encode Speed[/]")
            speed_map = {
                "1":"ultrafast","2":"superfast","3":"veryfast","4":"faster",
                "5":"fast","6":"medium","7":"slow","8":"slower","9":"veryslow",
            }
            for k,v in speed_map.items(): console.print(f"  [cyan]{k}[/]  {v}")
            sp = Prompt.ask("Speed", choices=list(speed_map.keys()), default="7")
            preset["speed"] = speed_map[sp]

        # Resolution
        vs   = video_stream(info) if info else None
        src_w = safe_int((vs or {}).get("width"))  if vs else None
        src_h = safe_int((vs or {}).get("height")) if vs else None
        preset["max_res"] = pick_resolution(src_w, src_h)

        # Extra filters
        console.print("\n[bold cyan]Optional Filters[/]")
        if Confirm.ask("  Deinterlace (interlaced source)?", default=False):
            preset["_deinterlace"] = True
        if Confirm.ask("  Noise reduction (hqdn3d)?", default=False):
            preset["_denoise"] = True
        if Confirm.ask("  Two-pass encoding (slower, more accurate bitrate)?",
                       default=preset.get("two_pass",False)):
            preset["two_pass"] = True

    # Audio
    console.print("\n[bold cyan]Audio Codec[/]")
    audio_opts = [
        ("aac","AAC — best compatibility (recommended)"),
        ("libopus","Opus — efficient, modern"),
        ("libmp3lame","MP3 — universal"),
        ("eac3","E-AC3 (Dolby Digital Plus)"),
        ("flac","FLAC — lossless"),
        ("copy","Copy audio unchanged"),
    ]
    tbl2 = Table(box=box.SIMPLE,padding=(0,1),show_header=False)
    tbl2.add_column("#",style="bold dim",width=3)
    tbl2.add_column("Codec")
    for i,(e,l) in enumerate(audio_opts,1): tbl2.add_row(str(i),l)
    console.print(tbl2)
    ac = Prompt.ask("Audio", choices=[str(i) for i in range(1,len(audio_opts)+1)], default="1")
    preset["audio_codec"] = audio_opts[int(ac)-1][0]
    if preset["audio_codec"] not in ("copy","flac"):
        console.print("  [dim]Guide: 64 · 96 · 128 · 192 · 256 · 320 kb/s[/]")
        preset["audio_kbps"] = int(Prompt.ask("Audio bitrate kb/s", default="128"))

    # Multi-track audio
    if info and len(all_audio_streams(info)) > 1:
        console.print(f"\n  [yellow]! {len(all_audio_streams(info))} audio tracks detected.[/]")
        if Confirm.ask("  Include all audio tracks?", default=True):
            preset["_all_audio"] = True

    return preset

# ════════════════════════════════════════════════════════════════════════
# INTERACTIVE PRESET CONFIGURATION
# ════════════════════════════════════════════════════════════════════════

def configure_preset(key: str, preset: dict, info: Optional[dict]) -> dict:
    preset = dict(preset)

    if key == "target_mb":
        console.print()
        console.print(Panel(
            "[dim]Two-pass encoding precisely hits your target.\n"
            "WhatsApp video (with preview): [bold]100 MB[/]  |  Telegram: [bold]2 GB[/]\n"
            "Rough guide: 50 MB ~ 3-5 min 720p  |  100 MB ~ 5-10 min 720p[/]",
            border_style="dim",title="[dim]Info[/]",
        ))
        preset["target_mb"] = float(Prompt.ask("Target file size (MB)", default="100"))
        preset["max_res"]   = pick_resolution(default_res=preset.get("max_res"))

    elif key == "target_percent":
        sz = file_size_bytes(info) if info else 0
        console.print()
        if sz > 0:
            console.print(f"  Source: [bold]{sz/1024/1024:.1f} MB[/]")
            console.print("  [dim]10 = tiny  |  30 = aggressively smaller  |  50 = half  |  80 = subtle[/]")
        pct = float(Prompt.ask("Keep what % of original size?", default="30"))
        preset["_pct"]      = pct/100.0
        preset["max_res"]   = pick_resolution(default_res=preset.get("max_res"))

    elif key == "whatsapp":
        console.print()
        console.print(
            "  [dim]WhatsApp video (with preview) limit: [bold]100 MB[/], [bold]720p[/] max.\n"
            "  Sent as [bold]document[/]: up to 2 GB, no preview.[/]"
        )
        as_doc = Confirm.ask("  Send as document (up to 2 GB, but no preview)?", default=False)
        if as_doc:
            preset["target_mb"] = None; preset["max_res"] = None
            preset["crf"]= 20; preset["two_pass"] = False
        else:
            preset["target_mb"] = float(Prompt.ask("  Target MB (default 95)", default="95"))

    elif key in ("compress_light","compress_medium","compress_heavy"):
        console.print()
        if Confirm.ask("  Change output resolution?", default=False):
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
    if not filters or not max_res:
        filters.append("scale=trunc(iw/2)*2:trunc(ih/2)*2")
    return filters

def build_cmd(input_path, output_path, preset, src_w, src_h,
              video_kbps=None, pass_num=0, passlog=None) -> List[str]:
    cmd = ["ffmpeg","-hide_banner","-y","-i",input_path]
    co  = preset["codec"]

    if co == "copy":
        ac = preset.get("audio_codec") or "aac"
        ab = preset.get("audio_kbps") or 192
        am = ["-map","0:v","-map","0:a"] if preset.get("_all_audio") else ["-map","0:v","-map","0:a?"]
        cmd += am + ["-c:v","copy"]
        cmd += ["-c:a","copy"] if ac=="copy" else ["-c:a",ac,"-b:a",f"{ab}k"]
        cmd += ["-movflags","+faststart",output_path]
        return cmd

    vf_list = build_vf_list(preset, src_w, src_h)
    if vf_list: cmd += ["-vf", ",".join(vf_list)]

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
        else:
            prog.stop()
            console.print(f"[red]  FFmpeg exited {proc.returncode}[/]")
            return False

# ════════════════════════════════════════════════════════════════════════
# ENCODE
# ════════════════════════════════════════════════════════════════════════

def encode_file(input_path, output_path, preset, info, idx=0, total=1) -> bool:
    duration = file_duration(info)
    vs       = video_stream(info)
    src_w    = safe_int((vs or {}).get("width"))  if vs else None
    src_h    = safe_int((vs or {}).get("height")) if vs else None
    label_p  = f"[{idx}/{total}] " if total > 1 else ""

    # Percent target
    if preset.get("_pct") and file_size_bytes(info) > 0 and duration > 0:
        preset = dict(preset)
        preset["target_mb"] = file_size_bytes(info)/1024/1024 * preset["_pct"]
        console.print(f"  [dim]Target: {preset['target_mb']:.1f} MB ({preset['_pct']*100:.0f}% of original)[/]")

    # Copy-video
    if preset["codec"] == "copy":
        cmd = build_cmd(input_path, output_path, preset, src_w, src_h)
        return run_with_progress(cmd, duration, f"{label_p}Remuxing")

    # Two-pass
    if preset.get("target_mb") and duration > 0:
        akbps   = preset.get("audio_kbps") or 128
        vkbps   = target_video_kbps(preset["target_mb"], duration, akbps)
        tmpdir  = tempfile.mkdtemp(prefix="fftoolbox_")
        passlog = os.path.join(tmpdir,"ff2pass")
        est_mb  = (vkbps+akbps)*1000*duration/(8*1024*1024)
        console.print(f"  [dim]Two-pass · target {preset['target_mb']:.0f} MB · video {vkbps} kb/s · audio {akbps} kb/s · est. {est_mb:.1f} MB[/]")
        cmd1 = build_cmd(input_path, output_path, preset, src_w, src_h, vkbps, 1, passlog)
        ok = run_with_progress(cmd1, duration, f"{label_p}Pass 1/2")
        if ok:
            cmd2 = build_cmd(input_path, output_path, preset, src_w, src_h, vkbps, 2, passlog)
            ok = run_with_progress(cmd2, duration, f"{label_p}Pass 2/2")
        try: shutil.rmtree(tmpdir)
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
    console.print(f"  [green]OK[/]  {human_size(src_sz)} -> [{clr}]{human_size(dst_sz)}[/]  ({abs(pct):.1f}% {direction})")
    dst_mb = dst_sz/1024/1024
    if preset_key == "whatsapp" and dst_mb > WHATSAPP_VIDEO_MB:
        console.print(
            f"\n  [bold yellow]! Output is {dst_mb:.1f} MB — over WhatsApp's {WHATSAPP_VIDEO_MB} MB video limit.[/]\n"
            "  [dim]Options: use [bold]Target File Size[/] at 95 MB, lower CRF/resolution,\n"
            "  or send as a [bold]document[/] in WhatsApp (no preview, up to 2 GB).[/]"
        )
    elif dst_sz > src_sz and dst_sz-src_sz > 1024*1024:
        console.print("  [yellow]! Output is larger than input — source may already be well compressed.[/]")

# ════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════

def main():
    print_banner()

    # Dependency check
    have_ffmpeg, have_ffprobe = check_deps()
    if not have_ffmpeg or not have_ffprobe:
        missing = (["ffmpeg"] if not have_ffmpeg else []) + (["ffprobe"] if not have_ffprobe else [])
        console.print(Panel(
            f"[bold red]Missing:[/] {', '.join(missing)}\n\n"
            "[dim]Ubuntu/Debian:  sudo apt install ffmpeg\n"
            "Arch:           sudo pacman -S ffmpeg\n"
            "macOS:          brew install ffmpeg\n"
            "Windows:        https://ffmpeg.org/download.html[/]",
            border_style="red",title="[red]Dependency Error[/]",
        ))
        sys.exit(1)

    hw = detect_hw_encoders()
    if hw:
        console.print("  [dim]Hardware encoders: " + ", ".join(l for _,l in hw[:3])
                      + ("[/]" if len(hw)<=3 else f" +{len(hw)-3} more[/]"))
        console.print()

    # STEP 1 — Files
    console.print(Rule("[bold]Step 1 · Select File(s)[/]"))
    console.print()
    console.print("  [cyan]1[/]  Browse interactively  [dim](recommended)[/]")
    console.print("  [cyan]2[/]  Paste file or directory path")
    console.print("  [cyan]3[/]  Entire directory  (batch mode)")
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
            files = sorted(str(f) for f in p.iterdir() if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS)
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
    if len(files) > 5: console.print(f"  [dim]... and {len(files)-5} more[/]")

    console.print()
    first_info = run_ffprobe(files[0])
    if first_info: print_file_info(first_info, files[0])
    else: console.print("[yellow]  Could not read media info for first file.[/]")

    # STEP 2 — Preset
    console.print()
    console.print(Rule("[bold]Step 2 · Choose Preset[/]"))
    console.print()
    suggested = suggest_preset(first_info) if first_info else "web_1080p"
    show_presets_table(suggested)
    preset_keys  = list(PRESETS.keys())
    suggested_no = str(preset_keys.index(suggested)+1)
    choice       = Prompt.ask("Preset number", choices=[str(i) for i in range(1,len(preset_keys)+1)], default=suggested_no)
    selected_key = preset_keys[int(choice)-1]
    preset       = dict(PRESETS[selected_key])

    tip = preset.get("tip","")
    if tip: console.print(f"\n  [dim]{tip}[/]")

    preset = configure_preset(selected_key, preset, first_info)
    color  = preset.get("color","cyan")
    console.print(f"\n  [green]OK[/]  [{color}]{preset.get('emoji','')} {preset['name']}[/]")

    # STEP 3 — Output dir
    output_dir = pick_output_dir(files[0])
    try: os.makedirs(output_dir, exist_ok=True)
    except OSError as e: console.print(f"[red]  Cannot create output dir: {e}[/]"); return
    console.print(f"  [green]OK[/]  Output: [dim]{escape(output_dir)}[/]")

    # STEP 4 — Plan
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
        fi = infos.get(f) or run_ffprobe(f)
        infos[f] = fi
        out = f"{Path(f).stem}_{selected_key}.mp4"
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

    # STEP 5 — Encode
    console.print()
    console.print(Rule("[bold cyan]Encoding[/]"))
    success, failed = 0, 0
    results: List[Tuple[str,str,int,int]] = []

    for i, fpath in enumerate(files, 1):
        console.print()
        console.print(f"  [bold][{i}/{len(files)}][/]  {escape(Path(fpath).name)}")
        fi = infos.get(fpath) or run_ffprobe(fpath)
        if not fi:
            console.print("  [red]  Could not read — skipping[/]"); failed += 1; continue

        file_preset = dict(preset)
        if preset.get("_pct") and file_size_bytes(fi) > 0:
            file_preset["target_mb"] = file_size_bytes(fi)/1024/1024 * preset["_pct"]

        out_name = f"{Path(fpath).stem}_{selected_key}.mp4"
        out_path = os.path.join(output_dir, out_name)
        if os.path.exists(out_path):
            out_path = os.path.join(output_dir, f"{Path(fpath).stem}_{selected_key}_{int(time.time())}.mp4")

        try:
            ok = encode_file(fpath, out_path, file_preset, fi, i, len(files))
        except Exception as exc:
            console.print(f"  [red]  Error: {exc}[/]")
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

    # STEP 6 — Summary
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
        console.print(f"  Total  {human_size(tin)} -> [{clr}]{human_size(tout)}[/]"
                      + (f"  [green](saved {human_size(saved)}, {pct:.1f}%)[/]" if saved > 0
                         else f"  [yellow](+{human_size(-saved)} larger)[/]"))
    console.print(f"\n  [bold]Output:[/] [cyan]{escape(output_dir)}[/]")
    console.print()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n\n  [yellow]Aborted. Goodbye![/]")
        sys.exit(1)
