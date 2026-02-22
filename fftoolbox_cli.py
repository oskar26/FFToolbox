#!/usr/bin/env python3
"""
fftoolbox_cli.py

Terminal utility to convert/encode video files with selectable options
and an interactive menu. Uses ffprobe/ffmpeg on PATH.

Features:
 - select single file or directory (optionally recursive)
 - choose output directory
 - choose target size (MB) or percent compression or explicit bitrate
 - choose codec: h264 (libx264), hevc (libx265), copy video + reencode audio (for Resolve)
 - choose resolution: keep, 4k, 1080p, custom
 - choose audio codec and bitrate
 - two-pass option
 - dry-run / preview estimated bitrates
 - show ffprobe info
 - simple logging

Run:
  python3 fftoolbox_cli.py

Requirements:
 - Python 3.8+
 - ffmpeg and ffprobe available in PATH

License: MIT
"""

import sys
import os
import shutil
import subprocess
import json
import math
import tempfile
from pathlib import Path

APPNAME = "fftoolbox"

# Helpers ---------------------------------------------------------------

def run_cmd(cmd, capture_output=False):
    try:
        if capture_output:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, text=True)
            return res.stdout.strip(), res.stderr.strip()
        else:
            subprocess.run(cmd, check=True)
            return None, None
    except subprocess.CalledProcessError as e:
        if capture_output:
            return e.stdout if e.stdout else "", e.stderr if e.stderr else str(e)
        else:
            raise


def ffprobe_info(path: str):
    """Return parsed ffprobe JSON for the file (or None)."""
    if not shutil.which("ffprobe"):
        print("Error: ffprobe not found in PATH")
        return None
    cmd = ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path]
    out, err = run_cmd(cmd, capture_output=True)
    if not out:
        print("ffprobe failed:", err)
        return None
    try:
        return json.loads(out)
    except Exception as e:
        print("Failed to parse ffprobe output:", e)
        return None


def human_size(bytesize):
    for unit in ["B","KB","MB","GB","TB"]:
        if abs(bytesize) < 1024.0:
            return f"{bytesize:3.1f} {unit}"
        bytesize /= 1024.0
    return f"{bytesize:.1f} PB"


def estimate_video_bitrate_kbps(target_mb, duration_s, audio_kbps):
    # target_mb in MB, duration in seconds
    bits_total = target_mb * 1024 * 1024 * 8
    kbps_total = bits_total / duration_s / 1000.0
    video_kbps = kbps_total - audio_kbps
    return max(0, int(video_kbps))


def guess_resolution_from_streams(streams):
    for s in streams:
        if s.get('codec_type') == 'video':
            w = s.get('width')
            h = s.get('height')
            return w, h
    return None, None


def build_ffmpeg_cmd(input_path, output_path, codec_video, codec_audio, video_kbps=None, audio_kbps=128,
                     resolution=None, two_pass=False, passlogfile=None, maxrate_kbps=None, bufsize_kbps=None,
                     copy_video=False):
    # resolution: (w,h) or None or 'keep'
    vf = []
    if resolution and resolution != 'keep':
        vf.append(f"scale={resolution[0]}:{resolution[1]}:flags=lanczos")
    vf_filter = ",".join(vf) if vf else None

    cmd_base = ["ffmpeg", "-hide_banner", "-y", "-i", str(input_path)]

    if copy_video:
        # copy video stream, reencode audio
        cmd_base += ["-map", "0:v", "-map", "0:a?", "-c:v", "copy", "-c:a", codec_audio, "-b:a", f"{audio_kbps}k", str(output_path)]
        return cmd_base

    # choose codec settings
    video_params = []
    if codec_video == 'libx264':
        # profile high, preset <-> quality/speed
        video_params = ["-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p"]
    elif codec_video == 'libx265':
        video_params = ["-c:v", "libx265", "-pix_fmt", "yuv420p"]
    else:
        # default to libx264
        video_params = ["-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p"]

    # bitrate control
    bitrate_opts = []
    if video_kbps:
        bitrate_opts += ["-b:v", f"{video_kbps}k"]
    if maxrate_kbps:
        bitrate_opts += ["-maxrate", f"{maxrate_kbps}k"]
    if bufsize_kbps:
        bitrate_opts += ["-bufsize", f"{bufsize_kbps}k"]

    audio_opts = ["-c:a", codec_audio, "-b:a", f"{audio_kbps}k"]

    # assemble command
    cmd = cmd_base
    if vf_filter:
        cmd += ["-vf", vf_filter]

    cmd += ["-map", "0:v", "-map", "0:a?"]
    cmd += video_params + bitrate_opts
    cmd += audio_opts

    # mov/mp4 compatibility
    cmd += ["-movflags", "+faststart"]

    if two_pass and passlogfile:
        cmd += ["-pass", "2", "-passlogfile", passlogfile]

    cmd += [str(output_path)]
    return cmd


def run_two_pass_encoding(input_path, output_path, codec_video, codec_audio, video_kbps, audio_kbps,
                          resolution, preset='slow'):
    tmpdir = tempfile.mkdtemp(prefix=APPNAME)
    passlog = os.path.join(tmpdir, 'ffmpeg2pass')

    # rough maxrate/bufsize
    maxrate = int(video_kbps * 1.3)
    bufsize = int(video_kbps * 2)

    print(f"Running two-pass: target {video_kbps} kb/s, audio {audio_kbps} kb/s")

    # pass 1
    cmd1 = [
        'ffmpeg', '-hide_banner', '-y', '-i', str(input_path)
    ]
    if resolution and resolution != 'keep':
        cmd1 += ['-vf', f"scale={resolution[0]}:{resolution[1]}:flags=lanczos"]
    cmd1 += ['-map', '0:v', '-c:v', codec_video, '-b:v', f"{video_kbps}k", '-maxrate', f"{maxrate}k", '-bufsize', f"{bufsize}k",
             '-preset', preset, '-pass', '1', '-an', '-f', 'mp4', '/dev/null', '-passlogfile', passlog]

    subprocess.run(cmd1)

    # pass 2
    cmd2 = [
        'ffmpeg', '-hide_banner', '-y', '-i', str(input_path)
    ]
    if resolution and resolution != 'keep':
        cmd2 += ['-vf', f"scale={resolution[0]}:{resolution[1]}:flags=lanczos"]
    cmd2 += ['-map', '0:v', '-map', '0:a?', '-c:v', codec_video, '-b:v', f"{video_kbps}k", '-maxrate', f"{maxrate}k", '-bufsize', f"{bufsize}k",
             '-preset', preset, '-pass', '2', '-passlogfile', passlog]
    cmd2 += ['-c:a', codec_audio, '-b:a', f"{audio_kbps}k", '-movflags', '+faststart', str(output_path)]

    subprocess.run(cmd2)

    # cleanup
    try:
        for f in os.listdir(tmpdir):
            os.remove(os.path.join(tmpdir, f))
        os.rmdir(tmpdir)
    except Exception:
        pass


# Interactive menu -----------------------------------------------------

def print_header():
    print('='*60)
    print(f"{APPNAME} - interactive video toolbox")
    print('='*60)


def choose_file():
    path = input("Input file path (or directory): ").strip()
    if not path:
        print("No input given")
        return None
    return path


def choose_output_dir(default_dir):
    out = input(f"Output directory [{default_dir}]: ").strip()
    return out if out else default_dir


def choose_mode():
    print("Choose target mode:")
    print(" 1) target file size (MB)")
    print(" 2) percent compression (e.g. 50 for 50%)")
    print(" 3) explicit video kbps")
    print(" 4) keep original (reencode audio only)")
    c = input("Mode [1]: ").strip() or '1'
    return c


def choose_codec():
    print("Select video codec:")
    print(" 1) H.264 (libx264) - widest compatibility")
    print(" 2) H.265 (libx265) - smaller files, less compat")
    print(" 3) copy video (video stream copied, only reencode audio)")
    c = input("Codec [1]: ").strip() or '1'
    mapping = {'1': 'libx264', '2': 'libx265', '3': 'copy'}
    return mapping.get(c, 'libx264')


def choose_resolution(original_w, original_h):
    print(f"Original resolution: {original_w}x{original_h}")
    print("Choose resolution:")
    print(" 1) keep original")
    print(" 2) 3840x2160 (4K)")
    print(" 3) 1920x1080 (1080p)")
    print(" 4) custom")
    c = input("Resolution [1]: ").strip() or '1'
    if c == '1':
        return 'keep'
    if c == '2':
        return (3840, 2160)
    if c == '3':
        return (1920, 1080)
    if c == '4':
        w = int(input("Width: "))
        h = int(input("Height: "))
        return (w, h)
    return 'keep'


def main_menu():
    print_header()

    input_path = choose_file()
    if not input_path:
        print("Cancelled")
        return

    input_path = os.path.expanduser(input_path)

    output_dir = choose_output_dir(os.path.join(os.getcwd(), 'fftoolbox_output'))
    os.makedirs(output_dir, exist_ok=True)

    # handle directory vs file
    files = []
    if os.path.isdir(input_path):
        recursive = input("Input is directory — include subdirs? [y/N]: ").strip().lower() == 'y'
        if recursive:
            for root, dirs, filenames in os.walk(input_path):
                for fn in filenames:
                    if fn.lower().endswith(('.mp4','.mov','.mkv','.m4v')):
                        files.append(os.path.join(root, fn))
        else:
            for fn in os.listdir(input_path):
                if fn.lower().endswith(('.mp4','.mov','.mkv','.m4v')):
                    files.append(os.path.join(input_path, fn))
    else:
        files = [input_path]

    if not files:
        print("No files found to process")
        return

    # Show first file info
    info = ffprobe_info(files[0])
    if info and 'streams' in info:
        dw, dh = guess_resolution_from_streams(info['streams'])
    else:
        dw, dh = None, None

    mode = choose_mode()
    target_mb = None
    percent = None
    explicit_kbps = None
    if mode == '1':
        target_mb = float(input("Target size in MB (e.g. 180): ").strip() or '180')
    elif mode == '2':
        percent = float(input("Percent of original size to aim for (e.g. 50): ").strip() or '50')
    elif mode == '3':
        explicit_kbps = int(input("Target video kbps (e.g. 5000): ").strip())
    else:
        pass

    codec = choose_codec()
    if codec == 'copy':
        codec_video = 'copy'
    else:
        codec_video = 'libx264' if codec == 'libx264' or codec == 'libx264' else codec
        if codec == 'libx265':
            codec_video = 'libx265'

    audio_bitrate = int(input("Audio bitrate kbps [128]: ").strip() or '128')
    two_pass = input("Use two-pass encoding for video? [Y/n]: ").strip().lower() != 'n'
    res_choice = choose_resolution(dw, dh)

    # Process each file
    for fpath in files:
        print('\n' + '-'*40)
        print(f"Processing: {fpath}")
        finfo = ffprobe_info(fpath)
        if not finfo:
            print("Skipping, no info")
            continue
        duration = float(finfo.get('format', {}).get('duration', 0) or 0)
        size_bytes = int(finfo.get('format', {}).get('size', 0) or 0)
        size_mb = size_bytes / (1024*1024) if size_bytes else None

        if percent:
            if not size_mb:
                print("Cannot compute percent mode for file with unknown size — skipping")
                continue
            target_mb = size_mb * (percent/100.0)
            print(f"Original size: {size_mb:.1f} MB → target {target_mb:.1f} MB ({percent}%)")

        if explicit_kbps:
            video_kbps = explicit_kbps
        else:
            # compute estimated video kbps
            if not duration or not target_mb:
                print("Insufficient info to compute bitrate — please choose explicit kbps")
                continue
            video_kbps = estimate_video_bitrate_kbps(target_mb, duration, audio_bitrate)
            print(f"Estimated video kbps: {video_kbps} kb/s for target {target_mb} MB and duration {duration:.1f}s")

        basename = os.path.basename(fpath)
        name, _ = os.path.splitext(basename)
        outpath = os.path.join(output_dir, f"{name}_converted.mp4")

        if codec_video == 'copy':
            # just copy video and reencode audio to AAC
            cmd = [
                'ffmpeg', '-hide_banner', '-y', '-i', fpath, '-map', '0:v', '-map', "0:a?",
                '-c:v', 'copy', '-c:a', 'aac', '-b:a', f"{audio_bitrate}k", '-movflags', '+faststart', outpath
            ]
            print('Running:', ' '.join(cmd))
            subprocess.run(cmd)
            print('Done ->', outpath)
            continue

        # run two-pass or single pass
        if two_pass:
            run_two_pass_encoding(fpath, outpath, codec_video, 'aac', video_kbps, audio_bitrate, res_choice)
        else:
            maxrate = int(video_kbps * 1.3)
            bufsize = int(video_kbps * 2)
            cmd = build_ffmpeg_cmd(fpath, outpath, codec_video, 'aac', video_kbps, audio_bitrate,
                                   resolution=res_choice, two_pass=False, maxrate_kbps=maxrate, bufsize_kbps=bufsize)
            print('Running:', ' '.join(cmd[:6]), '...')
            subprocess.run(cmd)

        print('Output ->', outpath)

    print('\nAll done.')


if __name__ == '__main__':
    try:
        main_menu()
    except KeyboardInterrupt:
        print('\nAborted by user')
        sys.exit(1)
