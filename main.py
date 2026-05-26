#!/usr/bin/env python3
"""
YouTube to MP4 Converter - Backend Server
Requirements: pip install flask yt-dlp flask-cors
Run: python server.py
"""

import os
import re
import json
import threading
from flask import Flask, request, jsonify, send_file, Response
from flask_cors import CORS
import yt_dlp

app = Flask(__name__)
CORS(app)

DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Progress tracking
progress_store = {}


def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "_", name)


@app.route("/api/info", methods=["POST"])
def get_video_info():
    """Fetch video metadata and available formats."""
    data = request.get_json()
    url = data.get("url", "").strip()

    if not url:
        return jsonify({"error": "URL tidak boleh kosong"}), 400

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        formats = []
        seen = set()

        for f in info.get("formats", []):
            height = f.get("height")
            ext = f.get("ext")
            vcodec = f.get("vcodec", "none")
            acodec = f.get("acodec", "none")
            filesize = f.get("filesize") or f.get("filesize_approx")

            # Only video formats with audio (or we'll merge)
            if not height or vcodec == "none":
                continue

            label = f"{height}p"
            if label not in seen:
                seen.add(label)
                formats.append({
                    "format_id": f["format_id"],
                    "label": label,
                    "height": height,
                    "ext": ext,
                    "filesize": filesize,
                    "filesize_str": _format_size(filesize) if filesize else "~",
                })

        formats.sort(key=lambda x: x["height"], reverse=True)

        return jsonify({
            "title": info.get("title", "Unknown"),
            "thumbnail": info.get("thumbnail", ""),
            "duration": _format_duration(info.get("duration", 0)),
            "uploader": info.get("uploader", "Unknown"),
            "view_count": _format_views(info.get("view_count", 0)),
            "formats": formats,
        })

    except yt_dlp.utils.DownloadError as e:
        return jsonify({"error": f"Gagal memuat video: {str(e)[:200]}"}), 400
    except Exception as e:
        return jsonify({"error": f"Terjadi kesalahan: {str(e)[:200]}"}), 500


@app.route("/api/download", methods=["POST"])
def download_video():
    """Download video with progress tracking."""
    data = request.get_json()
    url = data.get("url", "").strip()
    format_id = data.get("format_id", "bestvideo+bestaudio/best")
    task_id = data.get("task_id", "default")

    if not url:
        return jsonify({"error": "URL tidak boleh kosong"}), 400

    progress_store[task_id] = {"status": "starting", "percent": 0, "speed": "", "eta": ""}

    def progress_hook(d):
        if d["status"] == "downloading":
            percent_str = d.get("_percent_str", "0%").strip().replace("%", "")
            try:
                percent = float(percent_str)
            except ValueError:
                percent = 0
            progress_store[task_id] = {
                "status": "downloading",
                "percent": percent,
                "speed": d.get("_speed_str", "").strip(),
                "eta": d.get("_eta_str", "").strip(),
                "filename": d.get("filename", ""),
            }
        elif d["status"] == "finished":
            progress_store[task_id] = {
                "status": "processing",
                "percent": 100,
                "speed": "",
                "eta": "",
                "filename": d.get("filename", ""),
            }

    ydl_opts = {
        "format": f"{format_id}+bestaudio/best" if "+" not in format_id else format_id,
        "outtmpl": os.path.join(DOWNLOAD_DIR, "%(title)s.%(ext)s"),
        "merge_output_format": "mp4",
        "progress_hooks": [progress_hook],
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [{
            "key": "FFmpegVideoConvertor",
            "preferedformat": "mp4",
        }],
    }

    result = {}

    def run_download():
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                # Handle merged filename
                base = os.path.splitext(filename)[0]
                mp4_file = base + ".mp4"
                if os.path.exists(mp4_file):
                    filename = mp4_file
                result["filename"] = filename
                result["title"] = info.get("title", "video")
            progress_store[task_id]["status"] = "done"
            progress_store[task_id]["filename"] = result.get("filename", "")
        except Exception as e:
            progress_store[task_id] = {"status": "error", "error": str(e)[:300]}

    thread = threading.Thread(target=run_download)
    thread.start()
    thread.join()  # Wait for completion (for direct download response)

    if progress_store[task_id].get("status") == "error":
        return jsonify({"error": progress_store[task_id].get("error")}), 500

    filename = progress_store[task_id].get("filename", "")
    title = result.get("title", "video")

    if not filename or not os.path.exists(filename):
        # Try to find the file
        for f in os.listdir(DOWNLOAD_DIR):
            if f.endswith(".mp4"):
                filename = os.path.join(DOWNLOAD_DIR, f)
                break

    if not filename or not os.path.exists(filename):
        return jsonify({"error": "File tidak ditemukan setelah download"}), 500

    safe_name = sanitize_filename(title) + ".mp4"

    return send_file(
        filename,
        as_attachment=True,
        download_name=safe_name,
        mimetype="video/mp4"
    )


@app.route("/api/progress/<task_id>", methods=["GET"])
def get_progress(task_id):
    """Get download progress for a task."""
    prog = progress_store.get(task_id, {"status": "unknown", "percent": 0})
    return jsonify(prog)


def _format_size(size_bytes):
    if not size_bytes:
        return "~"
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def _format_duration(seconds):
    if not seconds:
        return "0:00"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _format_views(views):
    if not views:
        return "0"
    if views >= 1_000_000:
        return f"{views/1_000_000:.1f}M"
    if views >= 1_000:
        return f"{views/1_000:.1f}K"
    return str(views)


if __name__ == "__main__":
    print("=" * 50)
    print("  YouTube to MP4 Converter - Server")
    print("  http://localhost:5000")
    print("  Buka index.html di browser Anda")
    print("=" * 50)
    app.run(debug=True, port=5000, threaded=True)