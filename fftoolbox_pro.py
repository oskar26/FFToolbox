#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║            FFToolbox Pro — Smart Video Converter             ║
║   Powered by FFmpeg  ·  Professional Terminal Interface      ║
╚══════════════════════════════════════════════════════════════╝

Workflows this solves:
  · DaVinci Resolve export cleanup  (10 GB ProRes → 200 MB H.264)
  · WhatsApp / Telegram sharing     (< 15 MB, 720p, wide compat)
  · Archive with H.265              (~40 % smaller than H.264)
  · Web / Social Media upload       (1080p, fast-start)
  · Batch conversion of directories
  · Audio-only re-encode            (video copy, fix codec issues)

Requirements:
  · Python 3.8+
  · ffmpeg and ffprobe in PATH
  · pip install rich   (auto-installed on first run)

Usage:
  python3 fftoolbox_pro.py
"""

import sys
import os
import re
import json
import math
import time
import shutil
import tempfile
import subprocess
from pathlib import Path
from datetime import timedelta
from typing import Optional, List, Tuple, Dict, Any

# ── Auto-install rich ────────────────────────────────────────────────────────

def _ensure_rich() -> None:
    try:
        import rich  # noqa: F401
    except ImportError:
        print("⚙  Installing 'rich' for beautiful UI (one-time setup)…")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "rich", "--quiet"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            print("✓  rich installed successfully.\n")
        except Exception as exc:
            print(f"ERROR: Could not install 'rich': {exc}")
            print("Please run:  pip install rich")
            sys.exit(1)

_ensure_rich()

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.rule import Rule
from rich.progress import (
    Progress, BarColumn, TextColumn,
    TimeRemainingColumn, TaskProgressColumn, SpinnerColumn,
)
from rich.prompt import Prompt, Confirm
from rich.live import Live
from rich.columns import Columns
from rich import box
from rich.align import Align
from rich.markup import escape

console = Console(highlight=False)

# ────────────────────────────────────────────────────────────────────────────
#  CONSTANTS
# ────────────────────────────────────────────────────────────────────────────

VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".mkv", ".m4v", ".avi", ".wmv",
    ".flv", ".webm", ".mxf", ".ts", ".mts", ".m2ts",
    ".mpg", ".mpeg", ".3gp", ".ogv",
}

PROFESSIONAL_CODECS = {
    "prores", "prores_ks", "dnxhd", "dnxhr",
    "mjpeg", "v210", "r10k", "r210", "cineform", "cfhd",
}

WHATSAPP_LIMIT_MB = 15.0   # practical safe limit

# ────────────────────────────────────────────────────────────────────────────
#  PRESETS
# ────────────────────────────────────────────────────────────────────────────

PRESETS: Dict[str, Dict[str, Any]] = {
    "whatsapp": {
        "name":           "WhatsApp / Telegram",
        "description":    "< 15 MB · 720p max · H.264 · universal compat",
        "emoji":          "📱",
        "codec":          "libx264",
        "crf":            28,
        "speed":          "slow",
        "audio_codec":    "aac",
        "audio_kbps":     96,
        "max_resolution": (1280, 720),
        "target_mb":      WHATSAPP_LIMIT_MB,
        "color":          "green",
        "tip":            "Targets < 15 MB for WhatsApp. Uses two-pass if needed.",
    },
    "resolve_cleanup": {
        "name":           "DaVinci Resolve Cleanup",
        "description":    "ProRes/DNxHR → H.264  ·  near-lossless quality",
        "emoji":          "🎬",
        "codec":          "libx264",
        "crf":            18,
        "speed":          "slow",
        "audio_codec":    "aac",
        "audio_kbps":     192,
        "max_resolution": None,
        "target_mb":      None,
        "color":          "cyan",
        "tip":            "CRF 18 = near-lossless. Great for archiving Resolve exports.",
    },
    "archive_h265": {
        "name":           "Archive Quality (H.265)",
        "description":    "CRF 18 · ~40 % smaller than H.264 · Apple/HEVC",
        "emoji":          "🗄️",
        "codec":          "libx265",
        "crf":            18,
        "speed":          "slow",
        "audio_codec":    "aac",
        "audio_kbps":     192,
        "max_resolution": None,
        "target_mb":      None,
        "color":          "blue",
        "tip":            "Best long-term archival format. Slower encode but great quality.",
    },
    "web_1080p": {
        "name":           "Web / Social Media (1080p)",
        "description":    "H.264 · CRF 23 · 1080p max · fast-start",
        "emoji":          "🌐",
        "codec":          "libx264",
        "crf":            23,
        "speed":          "slow",
        "audio_codec":    "aac",
        "audio_kbps":     128,
        "max_resolution": (1920, 1080),
        "target_mb":      None,
        "color":          "yellow",
        "tip":            "Good balance of quality/size for YouTube, Vimeo, Instagram.",
    },
    "quick_convert": {
        "name":           "Quick Convert (fast)",
        "description":    "H.264 · CRF 23 · medium speed · all resolutions",
        "emoji":          "⚡",
        "codec":          "libx264",
        "crf":            23,
        "speed":          "medium",
        "audio_codec":    "aac",
        "audio_kbps":     128,
        "max_resolution": None,
        "target_mb":      None,
        "color":          "magenta",
        "tip":            "Fast encoding with good quality. Great for quick shares.",
    },
    "audio_recode": {
        "name":           "Fix Audio (copy video)",
        "description":    "Video stream copied · audio reencoded to AAC",
        "emoji":          "🔊",
        "codec":          "copy",
        "crf":            None,
        "speed":          None,
        "audio_codec":    "aac",
        "audio_kbps":     192,
        "max_resolution": None,
        "target_mb":      None,
        "color":          "white",
        "tip":            "Instant! Only audio is reencoded. Fixes codec compatibility issues.",
    },
    "target_size": {
        "name":           "Target File Size",
        "description":    "You specify MB → two-pass bitrate encoding",
        "emoji":          "📦",
        "codec":          "libx264",
        "crf":            None,
        "speed":          "slow",
        "audio_codec":    "aac",
        "audio_kbps":     128,
        "max_resolution": None,
        "target_mb":      None,   # set interactively
        "color":          "red",
        "tip":            "Precise file size control via two-pass encoding.",
    },
    "custom": {
        "name":           "Custom",
        "description":    "Configure every parameter yourself",
        "emoji":          "⚙️",
        "codec":          None,
        "crf":            None,
        "speed":          None,
        "audio_codec":    None,
        "audio_kbps":     None,
        "max_resolution": None,
        "target_mb":      None,
        "color":          "dim white",
        "tip":            "Full manual control.",
    },
}

# ────────────────────────────────────────────────────────────────────────────
#  UTILITIES
# ────────────────────────────────────────────────────────────────────────────

def human_size(b: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(b) < 1024.0:
            return f"{b:6.1f} {unit}"
        b /= 1024.0
    return f"{b:.1f} PB"


def human_dur(secs: float) -> str:
    return str(timedelta(seconds=int(secs)))


def check_deps() -> Tuple[bool, bool]:
    return bool(shutil.which("ffmpeg")), bool(shutil.which("ffprobe"))


def ffprobe(path: str) -> Optional[dict]:
    cmd = [
        "ffprobe", "-v", "error",
        "-print_format", "json",
        "-show_format", "-show_streams", path,
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             check=True, text=True)
        return json.loads(res.stdout)
    except Exception:
        return None


def video_stream(info: dict) -> Optional[dict]:
    for s in info.get("streams", []):
        if s.get("codec_type") == "video":
            return s
    return None


def audio_stream(info: dict) -> Optional[dict]:
    for s in info.get("streams", []):
        if s.get("codec_type") == "audio":
            return s
    return None


def codec_names(info: dict) -> Tuple[str, str]:
    vs = video_stream(info)
    as_ = audio_stream(info)
    vc = vs.get("codec_name", "unknown") if vs else "none"
    ac = as_.get("codec_name", "unknown") if as_ else "none"
    return vc, ac


def is_professional_export(info: dict) -> bool:
    vc, _ = codec_names(info)
    return any(p in vc.lower() for p in PROFESSIONAL_CODECS)


def file_duration(info: dict) -> float:
    return float(info.get("format", {}).get("duration") or 0)


def file_size_bytes(info: dict) -> int:
    return int(info.get("format", {}).get("size") or 0)


def fps_from_stream(vs: dict) -> str:
    raw = vs.get("r_frame_rate", "?")
    try:
        num, den = raw.split("/")
        return f"{int(num) / int(den):.3g}"
    except Exception:
        return raw


def scale_filter(src_w: int, src_h: int, max_res: Tuple[int, int]) -> Optional[str]:
    """Return ffmpeg scale vf string, or None if not needed."""
    mw, mh = max_res
    if src_w <= mw and src_h <= mh:
        return None
    ratio = min(mw / src_w, mh / src_h)
    nw = (int(src_w * ratio) // 2) * 2
    nh = (int(src_h * ratio) // 2) * 2
    return f"scale={nw}:{nh}:flags=lanczos"


def target_video_kbps(target_mb: float, duration_s: float, audio_kbps: int) -> int:
    bits_total = target_mb * 8 * 1024 * 1024
    kbps_total = bits_total / duration_s / 1000
    return max(150, int(kbps_total - audio_kbps))


def parse_progress_time(line: str) -> Optional[float]:
    m = re.search(r"time=(\d+):(\d+):([\d.]+)", line)
    if m:
        h, mn, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
        return h * 3600 + mn * 60 + s
    return None


def detect_hw_encoders() -> List[Tuple[str, str]]:
    """Returns list of (encoder_name, label) that ffmpeg supports."""
    candidates = [
        ("h264_nvenc",  "NVIDIA NVENC H.264"),
        ("hevc_nvenc",  "NVIDIA NVENC H.265"),
        ("h264_vaapi",  "VAAPI H.264 (Intel/AMD)"),
        ("hevc_vaapi",  "VAAPI H.265 (Intel/AMD)"),
        ("h264_qsv",    "Intel QuickSync H.264"),
    ]
    try:
        res = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        out = res.stdout
        return [(enc, lbl) for enc, lbl in candidates if enc in out]
    except Exception:
        return []


# ────────────────────────────────────────────────────────────────────────────
#  UI HELPERS
# ────────────────────────────────────────────────────────────────────────────

def print_banner() -> None:
    console.print()
    console.print(
        Panel.fit(
            Align.center(
                "[bold cyan]FFToolbox[/][bold white] Pro[/]  [dim]│[/]  "
                "[italic]Smart Video Converter[/]\n"
                "[dim]Powered by FFmpeg  ·  Professional Terminal Interface[/]"
            ),
            border_style="cyan",
            padding=(0, 6),
        )
    )
    console.print()


def print_file_info(info: dict, path: str) -> None:
    vc, ac = codec_names(info)
    vs = video_stream(info)
    dur = file_duration(info)
    sz  = file_size_bytes(info)

    tbl = Table(box=box.ROUNDED, border_style="dim", show_header=False, padding=(0, 1))
    tbl.add_column("K", style="bold cyan", width=16)
    tbl.add_column("V", style="white")

    tbl.add_row("Filename",  escape(Path(path).name))
    tbl.add_row("Size",      human_size(sz))
    tbl.add_row("Duration",  human_dur(dur))

    if vs:
        w, h = vs.get("width", "?"), vs.get("height", "?")
        tbl.add_row("Resolution", f"{w} × {h}")
        tbl.add_row("FPS",        fps_from_stream(vs))

    vc_display = vc.upper()
    if any(p in vc.lower() for p in PROFESSIONAL_CODECS):
        vc_display = f"[bold yellow]⚠  {vc.upper()}  (professional codec)[/]"
    tbl.add_row("Video codec",  vc_display)
    tbl.add_row("Audio codec",  ac.upper())

    if sz > 500 * 1024 * 1024:
        tbl.add_row("Note", "[bold yellow]Large file — DaVinci Resolve Cleanup preset recommended[/]")

    console.print(Panel(tbl, title="[bold]Source File[/]", border_style="cyan", padding=(0, 1)))


def show_presets_table(suggested_key: Optional[str] = None) -> None:
    tbl = Table(box=box.SIMPLE_HEAD, border_style="dim", padding=(0, 1))
    tbl.add_column("#",       style="bold dim", width=3)
    tbl.add_column("Preset",  width=30)
    tbl.add_column("Description")

    for i, (key, p) in enumerate(PRESETS.items(), 1):
        marker = " [bold cyan]← suggested[/]" if key == suggested_key else ""
        tbl.add_row(
            str(i),
            f"[{p['color']}]{p['emoji']}  {p['name']}[/]{marker}",
            f"[dim]{p['description']}[/]",
        )
    console.print(Panel(tbl, title="[bold]Conversion Presets[/]", border_style="cyan"))


def suggest_preset(info: dict) -> str:
    if is_professional_export(info) or file_size_bytes(info) > 500 * 1024 * 1024:
        return "resolve_cleanup"
    return "web_1080p"


# ────────────────────────────────────────────────────────────────────────────
#  INTERACTIVE FILE BROWSER
# ────────────────────────────────────────────────────────────────────────────

def file_browser(start: str = "~") -> Optional[List[str]]:
    """
    Keyboard-friendly numbered file browser.
    Returns list of selected file paths, or None if cancelled.
    """
    current = Path(os.path.expanduser(start)).resolve()

    while True:
        console.print()
        console.print(Rule(f"[bold cyan]File Browser[/]  [dim]{escape(str(current))}[/]"))

        try:
            raw_entries = sorted(current.iterdir(),
                                 key=lambda p: (p.is_file(), p.name.lower()))
        except PermissionError:
            console.print("[red]  Permission denied — going up[/]")
            current = current.parent
            continue

        dirs   = [e for e in raw_entries if e.is_dir()  and not e.name.startswith(".")]
        videos = [e for e in raw_entries if e.is_file() and e.suffix.lower() in VIDEO_EXTENSIONS]

        items: List[Tuple[str, Path, bool]] = []  # (label, path, is_dir)

        tbl = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
        tbl.add_column("#",    style="bold dim", width=4)
        tbl.add_column("Name", width=46)
        tbl.add_column("Size", style="dim", width=10)
        tbl.add_column("Type", style="dim", width=8)

        # ─ parent dir
        tbl.add_row("0", "[bold]📁  .. (up)[/]", "", "")
        items.append(("up", current.parent, True))

        # ─ subdirectories (max 30)
        for d in dirs[:30]:
            n = len(items)
            tbl.add_row(str(n), f"[yellow]📁  {escape(d.name)}[/]", "", "DIR")
            items.append((d.name, d, True))

        # ─ video files
        if not videos:
            tbl.add_row("", "[dim italic]  (no video files here)[/]", "", "")
        for v in videos:
            n = len(items)
            sz = v.stat().st_size
            tbl.add_row(
                str(n),
                f"[green]🎬  {escape(v.name)}[/]",
                human_size(sz),
                v.suffix.upper().lstrip("."),
            )
            items.append((v.name, v, False))

        console.print(tbl)
        console.print()
        console.print(
            "[dim]  [bold]Number[/] → open/select   [bold]a[/] → select all videos   "
            "[bold]p[/] → paste path   [bold]q[/] → cancel[/]"
        )

        choice = Prompt.ask("[bold cyan]>[/]").strip().lower()

        if choice == "q":
            return None

        if choice == "a":
            if videos:
                console.print(f"[green]✓  {len(videos)} video file(s) selected[/]")
                return [str(v) for v in videos]
            console.print("[yellow]No video files in this directory.[/]")
            continue

        if choice == "p":
            raw = Prompt.ask("Paste or type path").strip()
            raw = os.path.expanduser(raw)
            p   = Path(raw)
            if p.is_dir():
                current = p.resolve()
            elif p.is_file():
                return [str(p)]
            else:
                console.print(f"[red]Not found: {raw}[/]")
            continue

        try:
            idx = int(choice)
        except ValueError:
            console.print("[red]Please enter a number.[/]")
            continue

        if idx < 0 or idx >= len(items):
            console.print(f"[red]Number out of range (0–{len(items)-1}).[/]")
            continue

        _, path, is_dir = items[idx]

        if is_dir:
            current = path.resolve()
        else:
            return [str(path)]


# ────────────────────────────────────────────────────────────────────────────
#  CUSTOM PRESET BUILDER
# ────────────────────────────────────────────────────────────────────────────

def build_custom_preset(info: Optional[dict]) -> dict:
    preset = {k: v for k, v in PRESETS["custom"].items()}

    console.print()
    console.print(Rule("[bold]Custom Configuration[/]"))

    # ─ Video codec
    console.print("\n[bold cyan]Video Codec[/]")
    console.print("  [cyan]1[/]  H.264 (libx264) — widest compatibility")
    console.print("  [cyan]2[/]  H.265 (libx265) — ~40 % smaller, modern devices")
    console.print("  [cyan]3[/]  Copy video stream (only recode audio, very fast)")

    hw = detect_hw_encoders()
    if hw:
        console.print(f"\n  [bold]Hardware encoders detected:[/]")
        for i, (enc, lbl) in enumerate(hw, 4):
            console.print(f"  [cyan]{i}[/]  {lbl} ({enc})")

    codec_choices = ["1", "2", "3"] + [str(i) for i in range(4, 4 + len(hw))]
    vc = Prompt.ask("Codec", choices=codec_choices, default="1")

    sw_map = {"1": "libx264", "2": "libx265", "3": "copy"}
    if vc in sw_map:
        preset["codec"] = sw_map[vc]
    else:
        preset["codec"] = hw[int(vc) - 4][0]

    if preset["codec"] != "copy":
        # ─ Quality mode
        console.print("\n[bold cyan]Quality Mode[/]")
        console.print("  [cyan]1[/]  CRF (constant quality — recommended)")
        console.print("  [cyan]2[/]  Target file size (two-pass bitrate)")
        qm = Prompt.ask("Mode", choices=["1", "2"], default="1")

        if qm == "1":
            console.print("\n[dim]  CRF guide: 18 = near-lossless · 23 = default · 28 = compact[/]")
            preset["crf"]       = int(Prompt.ask("CRF value", default="23"))
            preset["target_mb"] = None
        else:
            preset["crf"]       = None
            preset["target_mb"] = float(Prompt.ask("Target size (MB)", default="200"))

        # ─ Encode speed
        console.print("\n[bold cyan]Encode Speed / Quality Trade-off[/]")
        speed_opts = {
            "1": "ultrafast",
            "2": "fast",
            "3": "medium",
            "4": "slow",
            "5": "veryslow",
        }
        for k, v in speed_opts.items():
            console.print(f"  [cyan]{k}[/]  {v}")
        sp = Prompt.ask("Speed", choices=list(speed_opts.keys()), default="4")
        preset["speed"] = speed_opts[sp]

        # ─ Resolution
        console.print("\n[bold cyan]Max Resolution (downscale only)[/]")
        console.print("  [cyan]1[/]  Keep original")
        console.print("  [cyan]2[/]  4K  (3840 × 2160)")
        console.print("  [cyan]3[/]  1080p  (1920 × 1080)")
        console.print("  [cyan]4[/]  720p   (1280 × 720)")
        console.print("  [cyan]5[/]  480p   (854 × 480)")
        console.print("  [cyan]6[/]  Custom")
        rv = Prompt.ask("Resolution", choices=["1","2","3","4","5","6"], default="1")
        res_map = {
            "1": None,
            "2": (3840, 2160),
            "3": (1920, 1080),
            "4": (1280, 720),
            "5": (854, 480),
        }
        if rv in res_map:
            preset["max_resolution"] = res_map[rv]
        else:
            w = int(Prompt.ask("  Width px"))
            h = int(Prompt.ask("  Height px"))
            preset["max_resolution"] = (w, h)

    # ─ Audio
    console.print("\n[bold cyan]Audio[/]")
    console.print("  [cyan]1[/]  AAC  (recommended, best compat)")
    console.print("  [cyan]2[/]  Opus (efficient, modern)")
    console.print("  [cyan]3[/]  MP3")
    console.print("  [cyan]4[/]  Copy audio stream")
    av = Prompt.ask("Audio codec", choices=["1","2","3","4"], default="1")
    audio_map = {"1": "aac", "2": "libopus", "3": "libmp3lame", "4": "copy"}
    preset["audio_codec"] = audio_map[av]

    if preset["audio_codec"] != "copy":
        preset["audio_kbps"] = int(Prompt.ask("Audio bitrate kbps", default="128"))

    preset["name"]  = "Custom"
    preset["emoji"] = "⚙️"
    preset["color"] = "white"
    return preset


def configure_target_size_preset() -> dict:
    preset = {k: v for k, v in PRESETS["target_size"].items()}
    console.print()
    console.print(Panel(
        "[dim]Two-pass encoding will hit the target size precisely.\n"
        "Common targets: 15 MB (WhatsApp)  50 MB  100 MB  500 MB[/]",
        border_style="dim",
    ))
    preset["target_mb"] = float(Prompt.ask("Target file size (MB)", default="50"))
    console.print("\n[bold cyan]Max Resolution[/]")
    console.print("  [cyan]1[/]  Keep original  [cyan]2[/]  1080p  [cyan]3[/]  720p  [cyan]4[/]  480p")
    rv = Prompt.ask("Resolution", choices=["1","2","3","4"], default="1")
    res_map = {"1": None, "2": (1920,1080), "3": (1280,720), "4": (854,480)}
    preset["max_resolution"] = res_map[rv]
    preset["audio_kbps"] = int(Prompt.ask("Audio kbps", default="128"))
    return preset


# ────────────────────────────────────────────────────────────────────────────
#  FFMPEG COMMAND BUILDER
# ────────────────────────────────────────────────────────────────────────────

def build_cmd(
    input_path: str,
    output_path: str,
    preset: dict,
    vf_str: Optional[str]     = None,
    video_kbps: Optional[int] = None,
    pass_num: int              = 0,
    passlog: Optional[str]    = None,
) -> List[str]:

    cmd = ["ffmpeg", "-hide_banner", "-y", "-i", input_path]

    # ── Copy-video shortcut ──────────────────────────────────────────────
    if preset["codec"] == "copy":
        a_codec = preset.get("audio_codec") or "aac"
        a_kbps  = preset.get("audio_kbps") or 192
        cmd += [
            "-map", "0:v", "-map", "0:a?",
            "-c:v", "copy",
            "-c:a", a_codec, "-b:a", f"{a_kbps}k",
            "-movflags", "+faststart",
            output_path,
        ]
        return cmd

    # ── Video filters ────────────────────────────────────────────────────
    vf_parts = []
    if vf_str:
        vf_parts.append(vf_str)
    # ensure even dimensions (avoids ffmpeg codec errors)
    if not vf_str:
        vf_parts.append("scale=trunc(iw/2)*2:trunc(ih/2)*2")

    cmd += ["-vf", ",".join(vf_parts)]
    cmd += ["-map", "0:v", "-map", "0:a?"]

    # ── Video codec ──────────────────────────────────────────────────────
    if preset["codec"] == "libx264":
        cmd += ["-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p"]
    elif preset["codec"] == "libx265":
        cmd += ["-c:v", "libx265", "-pix_fmt", "yuv420p", "-tag:v", "hvc1"]
    else:
        # hardware encoder or other — use as-is
        cmd += ["-c:v", preset["codec"], "-pix_fmt", "yuv420p"]

    # ── Quality / Bitrate ────────────────────────────────────────────────
    if video_kbps:
        maxrate = int(video_kbps * 1.3)
        bufsize = int(video_kbps * 2.0)
        cmd += [
            "-b:v", f"{video_kbps}k",
            "-maxrate", f"{maxrate}k",
            "-bufsize", f"{bufsize}k",
        ]
    elif preset.get("crf") is not None:
        # libx265 uses -x265-params crf= alternatively, but -crf works too
        cmd += ["-crf", str(preset["crf"])]

    # ── Speed preset ─────────────────────────────────────────────────────
    if preset.get("speed") and "nvenc" not in preset["codec"] and "vaapi" not in preset["codec"]:
        cmd += ["-preset", preset["speed"]]

    # ── Two-pass control ─────────────────────────────────────────────────
    if pass_num == 1:
        cmd += ["-pass", "1", "-passlogfile", passlog,
                "-an", "-f", "mp4", "/dev/null"]
        return cmd
    elif pass_num == 2:
        cmd += ["-pass", "2", "-passlogfile", passlog]

    # ── Audio ────────────────────────────────────────────────────────────
    ac = preset.get("audio_codec") or "aac"
    if ac == "copy":
        cmd += ["-c:a", "copy"]
    else:
        cmd += ["-c:a", ac, "-b:a", f"{preset.get('audio_kbps', 128)}k"]

    cmd += ["-movflags", "+faststart"]
    cmd += [output_path]
    return cmd


# ────────────────────────────────────────────────────────────────────────────
#  ENCODING WITH LIVE PROGRESS
# ────────────────────────────────────────────────────────────────────────────

def run_with_progress(cmd: List[str], duration_s: float, label: str = "Encoding") -> bool:
    """Run ffmpeg and display a live progress bar. Returns True on success."""

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(bar_width=38, complete_style="cyan", finished_style="green"),
        TaskProgressColumn(),
        TextColumn("[dim]{task.fields[eta]}"),
        TextColumn("[dim]{task.fields[speed]}"),
        console=console,
        transient=False,
    ) as prog:
        task = prog.add_task(label, total=100, eta="", speed="")

        proc = subprocess.Popen(
            cmd,
            stderr=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            text=True,
        )

        for line in proc.stderr:
            t = parse_progress_time(line)
            if t and duration_s > 0:
                pct = min(99.9, t / duration_s * 100)
                sm  = re.search(r"speed=\s*([\d.]+)x", line)
                sp  = f"{sm.group(1)}×" if sm else ""
                remaining = max(0, (duration_s - t) / float(sm.group(1)) if sm and sm.group(1) != "0" else 0)
                eta_str = f"ETA {human_dur(remaining)}" if remaining > 2 else ""
                prog.update(task, completed=pct, speed=sp, eta=eta_str)

        proc.wait()
        if proc.returncode == 0:
            prog.update(task, completed=100, eta="", speed="✓ done")
            return True
        else:
            prog.stop()
            console.print(f"[red]  ✗ FFmpeg exited with code {proc.returncode}[/]")
            return False


def encode_file(
    input_path: str,
    output_path: str,
    preset: dict,
    info: dict,
) -> bool:
    """High-level encode function. Chooses CRF or two-pass as needed."""

    duration = file_duration(info)
    vs       = video_stream(info)
    src_w    = vs.get("width")  if vs else None
    src_h    = vs.get("height") if vs else None

    # ── Compute scale filter ─────────────────────────────────────────────
    vf = None
    if preset.get("max_resolution") and src_w and src_h:
        vf = scale_filter(src_w, src_h, preset["max_resolution"])

    # ── Copy-video path ──────────────────────────────────────────────────
    if preset["codec"] == "copy":
        cmd = build_cmd(input_path, output_path, preset)
        return run_with_progress(cmd, duration, "Remuxing")

    # ── Two-pass (target size) ───────────────────────────────────────────
    if preset.get("target_mb") and duration > 0:
        akbps     = preset.get("audio_kbps") or 128
        vkbps     = target_video_kbps(preset["target_mb"], duration, akbps)
        tmpdir    = tempfile.mkdtemp(prefix="fftoolbox_")
        passlog   = os.path.join(tmpdir, "ffpass")

        est_mb = (vkbps + akbps) * 1000 * duration / (8 * 1024 * 1024)
        console.print(
            f"  [dim]Target {preset['target_mb']} MB → video {vkbps} kb/s + audio {akbps} kb/s"
            f" → est. {est_mb:.1f} MB[/]"
        )

        cmd1 = build_cmd(input_path, output_path, preset, vf, vkbps, pass_num=1, passlog=passlog)
        ok   = run_with_progress(cmd1, duration, "Pass 1/2")

        if ok:
            cmd2 = build_cmd(input_path, output_path, preset, vf, vkbps, pass_num=2, passlog=passlog)
            ok   = run_with_progress(cmd2, duration, "Pass 2/2")

        try:
            shutil.rmtree(tmpdir)
        except Exception:
            pass
        return ok

    # ── CRF single-pass ──────────────────────────────────────────────────
    cmd = build_cmd(input_path, output_path, preset, vf)
    return run_with_progress(cmd, duration, "Encoding")


# ────────────────────────────────────────────────────────────────────────────
#  OUTPUT DIR PICKER
# ────────────────────────────────────────────────────────────────────────────

def pick_output_dir(first_file: str) -> str:
    src_dir = Path(first_file).parent
    default = str(src_dir / "fftoolbox_output")
    desktop = os.path.expanduser("~/Desktop/fftoolbox_output")

    console.print()
    console.print("[bold cyan]Output directory[/]")
    console.print(f"  [cyan]1[/]  Next to source files  [dim]({escape(default)})[/]")
    console.print(f"  [cyan]2[/]  Desktop               [dim]({escape(desktop)})[/]")
    console.print("  [cyan]3[/]  Custom path")

    c = Prompt.ask("Choice", choices=["1","2","3"], default="1")

    if c == "1":
        return default
    if c == "2":
        return desktop

    raw = Prompt.ask("Path").strip()
    return os.path.expanduser(raw)


# ────────────────────────────────────────────────────────────────────────────
#  POST-ENCODE CHECKS
# ────────────────────────────────────────────────────────────────────────────

def whatsapp_warn(output_path: str) -> None:
    try:
        sz_mb = os.path.getsize(output_path) / (1024 * 1024)
        if sz_mb > WHATSAPP_LIMIT_MB:
            console.print(
                f"\n  [bold yellow]⚠  Output is {sz_mb:.1f} MB — still above "
                f"WhatsApp's ~{WHATSAPP_LIMIT_MB:.0f} MB limit.[/]\n"
                "  [dim]Try the [bold]Target File Size[/dim][dim] preset "
                f"with {WHATSAPP_LIMIT_MB:.0f} MB, or lower the CRF / resolution.[/]"
            )
    except Exception:
        pass


# ────────────────────────────────────────────────────────────────────────────
#  MAIN
# ────────────────────────────────────────────────────────────────────────────

def main() -> None:
    print_banner()

    # ── Dependency check ─────────────────────────────────────────────────
    have_ffmpeg, have_ffprobe = check_deps()
    if not have_ffmpeg or not have_ffprobe:
        missing = (["ffmpeg"] if not have_ffmpeg else []) + (["ffprobe"] if not have_ffprobe else [])
        console.print(
            Panel(
                f"[bold red]Missing required tools:[/] {', '.join(missing)}\n\n"
                "[dim]Install with:\n"
                "  Ubuntu/Debian:  sudo apt install ffmpeg\n"
                "  Arch:           sudo pacman -S ffmpeg\n"
                "  macOS:          brew install ffmpeg\n"
                "  Windows:        https://ffmpeg.org/download.html[/]",
                border_style="red",
                title="[red]Dependency Error[/]",
            )
        )
        sys.exit(1)

    # ══════════════════════════════════════════════════════════════════════
    #  STEP 1 — File Selection
    # ══════════════════════════════════════════════════════════════════════
    console.print(Rule("[bold]Step 1 · Select File(s)[/]"))
    console.print()
    console.print("  [cyan]1[/]  Browse files interactively  [dim](recommended)[/]")
    console.print("  [cyan]2[/]  Paste a file or directory path")
    console.print("  [cyan]3[/]  Select an entire directory  (batch)")

    sel = Prompt.ask("How to select", choices=["1","2","3"], default="1")

    files: List[str] = []

    if sel == "1":
        result = file_browser(os.path.expanduser("~"))
        if not result:
            console.print("[yellow]No file selected. Exiting.[/]")
            return
        files = result

    elif sel == "2":
        raw = Prompt.ask("Path").strip()
        raw = os.path.expanduser(raw)
        p   = Path(raw)
        if p.is_file():
            files = [str(p)]
        elif p.is_dir():
            files = [str(f) for f in sorted(p.iterdir())
                     if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS]
        else:
            console.print(f"[red]Not found: {raw}[/]")
            return

    elif sel == "3":
        raw = Prompt.ask("Directory path").strip()
        raw = os.path.expanduser(raw)
        p   = Path(raw)
        if not p.is_dir():
            console.print(f"[red]Not a directory: {raw}[/]")
            return
        recursive = Confirm.ask("Include subdirectories?", default=False)
        glob = p.rglob("*") if recursive else p.iterdir()
        files = [str(f) for f in sorted(glob)
                 if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS]

    if not files:
        console.print("[red]No video files found. Exiting.[/]")
        return

    files = sorted(set(files))
    console.print(f"\n[green]✓[/] [bold]{len(files)} file(s) selected[/]")
    if len(files) > 1:
        for f in files[:5]:
            console.print(f"  [dim]{escape(f)}[/]")
        if len(files) > 5:
            console.print(f"  [dim]… and {len(files)-5} more[/]")

    # ── Probe first file ─────────────────────────────────────────────────
    console.print()
    first_info = ffprobe(files[0])
    if first_info:
        print_file_info(first_info, files[0])
    else:
        console.print("[yellow]Warning: could not read media info for first file.[/]")

    # ══════════════════════════════════════════════════════════════════════
    #  STEP 2 — Preset Selection
    # ══════════════════════════════════════════════════════════════════════
    console.print()
    console.print(Rule("[bold]Step 2 · Choose Preset[/]"))
    console.print()

    suggested = suggest_preset(first_info) if first_info else "web_1080p"
    show_presets_table(suggested)

    preset_keys   = list(PRESETS.keys())
    suggested_idx = preset_keys.index(suggested) + 1
    valid         = [str(i) for i in range(1, len(preset_keys) + 1)]
    choice        = Prompt.ask("Preset number", choices=valid, default=str(suggested_idx))

    selected_key  = preset_keys[int(choice) - 1]
    preset        = dict(PRESETS[selected_key])

    # Extra configuration for special presets
    if selected_key == "custom":
        preset = build_custom_preset(first_info)
    elif selected_key == "target_size":
        preset = configure_target_size_preset()

    color = preset.get("color", "cyan")
    console.print(
        f"\n[green]✓[/] Preset: [{color}]{preset.get('emoji','')} {preset['name']}[/]  "
        f"[dim]{preset.get('tip', '')}[/]"
    )

    # ══════════════════════════════════════════════════════════════════════
    #  STEP 3 — Output Directory
    # ══════════════════════════════════════════════════════════════════════
    output_dir = pick_output_dir(files[0])
    os.makedirs(output_dir, exist_ok=True)
    console.print(f"[green]✓[/] Output: [dim]{escape(output_dir)}[/]")

    # ══════════════════════════════════════════════════════════════════════
    #  STEP 4 — Encode Plan Preview
    # ══════════════════════════════════════════════════════════════════════
    console.print()
    console.print(Rule("[bold]Encode Plan[/]"))

    plan_tbl = Table(box=box.SIMPLE, padding=(0, 1))
    plan_tbl.add_column("File",     max_width=36, overflow="fold")
    plan_tbl.add_column("Size",     style="dim", width=10)
    plan_tbl.add_column("Duration", style="dim", width=10)
    plan_tbl.add_column("Output",   max_width=32, overflow="fold")

    total_src_sz = 0
    for f in files:
        fi   = ffprobe(f) if f != files[0] else first_info
        name = Path(f).name
        stem = Path(f).stem
        out  = f"{stem}_{selected_key}.mp4"
        if fi:
            sz  = file_size_bytes(fi)
            dur = file_duration(fi)
            total_src_sz += sz
            plan_tbl.add_row(name, human_size(sz), human_dur(dur), out)
        else:
            plan_tbl.add_row(name, "?", "?", out)

    console.print(plan_tbl)

    if total_src_sz > 0:
        console.print(f"[dim]Total input: {human_size(total_src_sz)}[/]")

    console.print()
    if not Confirm.ask("[bold]Start encoding now?[/]", default=True):
        console.print("[yellow]Cancelled.[/]")
        return

    # ══════════════════════════════════════════════════════════════════════
    #  STEP 5 — Encode
    # ══════════════════════════════════════════════════════════════════════
    console.print()
    console.print(Rule("[bold cyan]Encoding[/]"))

    success, failed = 0, 0
    results: List[Tuple[str, str, int, int]] = []

    for i, fpath in enumerate(files, 1):
        console.print()
        console.print(f"  [bold dim][{i}/{len(files)}][/]  {escape(Path(fpath).name)}")

        fi = ffprobe(fpath) if fpath != files[0] else first_info
        if not fi:
            console.print("  [red]✗ Could not read file info — skipping[/]")
            failed += 1
            continue

        stem     = Path(fpath).stem
        out_name = f"{stem}_{selected_key}.mp4"
        out_path = os.path.join(output_dir, out_name)

        ok = encode_file(fpath, out_path, preset, fi)

        if ok and os.path.exists(out_path):
            src_sz = file_size_bytes(fi)
            dst_sz = os.path.getsize(out_path)
            pct    = (1 - dst_sz / src_sz) * 100 if src_sz > 0 else 0
            clr    = "green" if pct > 0 else "yellow"
            console.print(
                f"  [green]✓[/]  {human_size(src_sz)} → [{clr}]{human_size(dst_sz)}[/]"
                f"  ({pct:+.1f} %)  [dim]{escape(out_path)}[/]"
            )
            if selected_key == "whatsapp":
                whatsapp_warn(out_path)
            success += 1
            results.append((fpath, out_path, src_sz, dst_sz))
        else:
            console.print(f"  [red]✗  Encoding failed[/]")
            failed += 1

    # ══════════════════════════════════════════════════════════════════════
    #  STEP 6 — Summary
    # ══════════════════════════════════════════════════════════════════════
    console.print()
    console.print(Rule("[bold]Summary[/]"))

    status_txt = f"[green]✓ {success} succeeded[/]"
    if failed:
        status_txt += f"  [red]✗ {failed} failed[/]"
    console.print(status_txt)

    if results:
        total_src = sum(r[2] for r in results)
        total_dst = sum(r[3] for r in results)
        pct       = (1 - total_dst / total_src) * 100 if total_src > 0 else 0
        clr       = "green" if pct > 0 else "yellow"
        console.print(
            f"Total  {human_size(total_src)} → [{clr}]{human_size(total_dst)}[/]  "
            f"({pct:+.1f} %  space saved)"
        )

    console.print(f"\n[bold]Files saved to:[/] [cyan]{escape(output_dir)}[/]")
    console.print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n\n[yellow]Aborted by user.[/]")
        sys.exit(1)
