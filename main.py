from flask import Flask, request, jsonify, send_file, after_this_request
from flask_cors import CORS
import yt_dlp
import os
import uuid
import threading
import time

app = Flask(__name__)
CORS(app)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Auto-delete file after 5 minutes
def delete_file_later(path, delay=300):
    def _delete():
        time.sleep(delay)
        try:
            os.remove(path)
        except:
            pass
    threading.Thread(target=_delete, daemon=True).start()

@app.route("/info", methods=["POST"])
def get_info():
    data = request.json
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL tidak boleh kosong"}), 400

    try:
        ydl_opts = {"quiet": True, "no_warnings": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        title = info.get("title", "Video")
        thumbnail = info.get("thumbnail", "")
        duration = info.get("duration", 0)
        minutes = duration // 60
        seconds = duration % 60

        # Collect available video resolutions
        formats = info.get("formats", [])
        available = set()
        for f in formats:
            h = f.get("height")
            if h and f.get("vcodec") != "none":
                available.add(h)

        resolutions = sorted(available, reverse=True)

        return jsonify({
            "title": title,
            "thumbnail": thumbnail,
            "duration": f"{minutes}:{seconds:02d}",
            "resolutions": resolutions
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/download", methods=["POST"])
def download_video():
    data = request.json
    url = data.get("url", "").strip()
    resolution = data.get("resolution", "best")

    if not url:
        return jsonify({"error": "URL tidak boleh kosong"}), 400

    file_id = str(uuid.uuid4())
    output_template = os.path.join(DOWNLOAD_DIR, f"{file_id}.%(ext)s")

    try:
        if resolution == "best":
            format_str = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
        else:
            h = int(resolution)
            format_str = (
                f"bestvideo[height<={h}][ext=mp4]+bestaudio[ext=m4a]"
                f"/bestvideo[height<={h}]+bestaudio"
                f"/best[height<={h}][ext=mp4]"
                f"/best[height<={h}]"
            )

        ydl_opts = {
            "format": format_str,
            "outtmpl": output_template,
            "quiet": True,
            "no_warnings": True,
            "merge_output_format": "mp4",
            "postprocessors": [{
                "key": "FFmpegVideoConvertor",
                "preferedformat": "mp4"
            }]
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "video")

        # Find the downloaded file
        downloaded = None
        for f in os.listdir(DOWNLOAD_DIR):
            if f.startswith(file_id):
                downloaded = os.path.join(DOWNLOAD_DIR, f)
                break

        if not downloaded:
            return jsonify({"error": "File tidak ditemukan setelah download"}), 500

        safe_title = "".join(c for c in title if c.isalnum() or c in " -_").strip()
        download_name = f"{safe_title}.mp4"

        delete_file_later(downloaded, delay=300)

        return send_file(
            downloaded,
            as_attachment=True,
            download_name=download_name,
            mimetype="video/mp4"
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    print("=" * 50)
    print("  YouTube → MP4 Converter Server")
    print("  Buka browser: http://localhost:5000")
    print("=" * 50)
    app.run(debug=False, host="0.0.0.0", port=5000)