import os
import re
import json
import subprocess
import tempfile
import threading
import time
from flask import Flask, request, jsonify, send_file, Response
from flask_cors import CORS

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

# Folder sementara untuk file download
DOWNLOAD_FOLDER = tempfile.mkdtemp()

# Simpan progress per job
job_status = {}
job_lock = threading.Lock()

def clean_youtube_url(url):
    """Validasi dan bersihkan URL YouTube"""
    patterns = [
        r'(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})',
        r'(https?://)?(www\.)?youtube\.com/shorts/([a-zA-Z0-9_-]{11})',
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return True
    return False

def get_best_resolution_format(url):
    """Ambil info video dan pilih resolusi terbaik yang tersedia"""
    try:
        result = subprocess.run(
            ['yt-dlp', '--dump-json', '--no-playlist', url],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return None, None

        info = json.loads(result.stdout)
        formats = info.get('formats', [])

        # Cari format video+audio terbaik
        best_height = 0
        for f in formats:
            if f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                h = f.get('height', 0) or 0
                if h > best_height:
                    best_height = h

        # Jika tidak ada format gabungan, cek video-only
        if best_height == 0:
            for f in formats:
                if f.get('vcodec') != 'none':
                    h = f.get('height', 0) or 0
                    if h > best_height:
                        best_height = h

        title = info.get('title', 'video')
        title = re.sub(r'[^\w\s-]', '', title).strip()
        title = re.sub(r'\s+', '_', title)[:50]

        return best_height, title
    except Exception as e:
        return None, None

def download_video(job_id, url):
    """Download video di background thread"""
    with job_lock:
        job_status[job_id] = {'status': 'starting', 'progress': 0, 'file': None, 'error': None}

    try:
        output_path = os.path.join(DOWNLOAD_FOLDER, f'{job_id}.mp4')

        # Format selector: ambil resolusi terbaik yang tersedia, merge jadi mp4
        format_selector = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best'

        cmd = [
            'yt-dlp',
            '--no-playlist',
            '-f', format_selector,
            '--merge-output-format', 'mp4',
            '--no-warnings',
            '--progress',
            '-o', output_path,
            url
        ]

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        for line in process.stdout:
            line = line.strip()
            # Parse progress dari output yt-dlp
            if '[download]' in line and '%' in line:
                try:
                    pct_match = re.search(r'(\d+\.?\d*)%', line)
                    if pct_match:
                        pct = float(pct_match.group(1))
                        with job_lock:
                            job_status[job_id]['progress'] = round(pct)
                            job_status[job_id]['status'] = 'downloading'
                except:
                    pass

        process.wait()

        if process.returncode == 0 and os.path.exists(output_path):
            with job_lock:
                job_status[job_id] = {
                    'status': 'done',
                    'progress': 100,
                    'file': output_path,
                    'error': None
                }
        else:
            with job_lock:
                job_status[job_id]['status'] = 'error'
                job_status[job_id]['error'] = 'Gagal mengunduh video. Periksa link dan coba lagi.'

    except Exception as e:
        with job_lock:
            job_status[job_id]['status'] = 'error'
            job_status[job_id]['error'] = str(e)


@app.route('/')
def index():
    return app.send_static_file('index.html')


@app.route('/api/info', methods=['POST'])
def get_info():
    """Ambil info video sebelum download"""
    data = request.json or {}
    url = (data.get('url') or '').strip()

    if not url:
        return jsonify({'error': 'Link tidak boleh kosong'}), 400

    if not clean_youtube_url(url):
        return jsonify({'error': 'Link YouTube tidak valid'}), 400

    try:
        result = subprocess.run(
            ['yt-dlp', '--dump-json', '--no-playlist', url],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return jsonify({'error': 'Video tidak ditemukan atau tidak bisa diakses'}), 400

        info = json.loads(result.stdout)
        formats = info.get('formats', [])

        # Cari resolusi terbaik
        heights = set()
        for f in formats:
            h = f.get('height')
            if h and f.get('vcodec') != 'none':
                heights.add(h)

        best_height = max(heights) if heights else 0

        # Format label resolusi
        res_label = f"{best_height}p" if best_height else "Terbaik"

        return jsonify({
            'title': info.get('title', 'Video YouTube'),
            'thumbnail': info.get('thumbnail', ''),
            'duration': info.get('duration_string', ''),
            'channel': info.get('channel', ''),
            'resolution': res_label,
            'valid': True
        })
    except Exception as e:
        return jsonify({'error': 'Terjadi kesalahan: ' + str(e)}), 500


@app.route('/api/download', methods=['POST'])
def start_download():
    """Mulai proses download"""
    data = request.json or {}
    url = (data.get('url') or '').strip()

    if not url or not clean_youtube_url(url):
        return jsonify({'error': 'Link tidak valid'}), 400

    # Buat job ID unik
    job_id = str(int(time.time() * 1000))

    # Jalankan download di background
    t = threading.Thread(target=download_video, args=(job_id, url))
    t.daemon = True
    t.start()

    return jsonify({'job_id': job_id})


@app.route('/api/progress/<job_id>')
def check_progress(job_id):
    """Cek status dan progress download"""
    with job_lock:
        status = job_status.get(job_id)

    if not status:
        return jsonify({'error': 'Job tidak ditemukan'}), 404

    return jsonify({
        'status': status['status'],
        'progress': status.get('progress', 0),
        'error': status.get('error')
    })


@app.route('/api/file/<job_id>')
def get_file(job_id):
    """Kirim file ke browser untuk diunduh"""
    with job_lock:
        status = job_status.get(job_id)

    if not status or status['status'] != 'done':
        return jsonify({'error': 'File belum siap'}), 404

    file_path = status['file']
    if not file_path or not os.path.exists(file_path):
        return jsonify({'error': 'File tidak ditemukan'}), 404

    def remove_after_send(path):
        time.sleep(60)
        try:
            os.remove(path)
        except:
            pass

    # Hapus file setelah 60 detik
    threading.Thread(target=remove_after_send, args=(file_path,), daemon=True).start()

    return send_file(
        file_path,
        mimetype='video/mp4',
        as_attachment=True,
        download_name='video.mp4'
    )


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🎬 YouTube to MP4 Converter berjalan di http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)