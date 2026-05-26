#!/usr/bin/env python3
"""
YouTube to MP4 Downloader
Menggunakan yt-dlp untuk mengunduh video YouTube ke format MP4.

Instalasi:
    pip install yt-dlp

Cara pakai:
    python youtube_to_mp4.py
    python youtube_to_mp4.py https://www.youtube.com/watch?v=xxx
    python youtube_to_mp4.py https://youtu.be/xxx --res 720
"""

import sys
import os
import re
import subprocess

# ─── Cek & install yt-dlp otomatis ───────────────────────────────────────────
def ensure_ytdlp():
    try:
        import yt_dlp
        return yt_dlp
    except ImportError:
        print("📦 yt-dlp belum terpasang. Memasang sekarang...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "yt-dlp", "-q"])
        import yt_dlp
        return yt_dlp

# ─── Konstanta resolusi ───────────────────────────────────────────────────────
RESOLUTIONS = {
    "1080": {"label": "1080p Full HD", "format": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best[height<=1080]"},
    "720":  {"label": "720p HD",       "format": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[height<=720]"},
    "480":  {"label": "480p Standar",  "format": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/best[height<=480]"},
    "360":  {"label": "360p Ringan",   "format": "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360][ext=mp4]/best[height<=360]"},
}

# ─── Validasi URL ─────────────────────────────────────────────────────────────
def is_valid_youtube_url(url):
    patterns = [
        r'(https?://)?(www\.)?(youtube\.com/watch\?v=[\w-]+)',
        r'(https?://)?(www\.)?(youtu\.be/[\w-]+)',
        r'(https?://)?(www\.)?(youtube\.com/shorts/[\w-]+)',
    ]
    return any(re.search(p, url) for p in patterns)

# ─── Deteksi resolusi terbaik ─────────────────────────────────────────────────
def detect_best_resolution(yt_dlp, url):
    print("\n🔍 Mendeteksi kualitas video yang tersedia...")
    ydl_opts = {"quiet": True, "no_warnings": True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = info.get("formats", [])

            available_heights = set()
            for f in formats:
                h = f.get("height")
                if h:
                    available_heights.add(h)

            # Pilih resolusi terbaik yang tersedia
            for res_key in ["1080", "720", "480", "360"]:
                target = int(res_key)
                if any(h >= target for h in available_heights):
                    return res_key, info.get("title", "Video")

            return "360", info.get("title", "Video")
    except Exception as e:
        print(f"  ⚠️  Tidak bisa mendeteksi otomatis: {e}")
        return "720", "Video"

# ─── Progress hook ────────────────────────────────────────────────────────────
def progress_hook(d):
    if d["status"] == "downloading":
        total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
        downloaded = d.get("downloaded_bytes", 0)
        speed = d.get("speed", 0)
        eta = d.get("eta", 0)

        if total > 0:
            pct = downloaded / total * 100
            bar_len = 30
            filled = int(bar_len * pct / 100)
            bar = "█" * filled + "░" * (bar_len - filled)
            speed_mb = (speed or 0) / 1_000_000
            print(f"\r  [{bar}] {pct:.1f}%  {speed_mb:.1f} MB/s  ETA {eta}s   ", end="", flush=True)
        else:
            dl_mb = downloaded / 1_000_000
            print(f"\r  ⬇️  Mengunduh... {dl_mb:.1f} MB", end="", flush=True)

    elif d["status"] == "finished":
        print(f"\n  ✅ Unduhan selesai! Menggabungkan file...")

    elif d["status"] == "error":
        print(f"\n  ❌ Terjadi kesalahan saat mengunduh.")

# ─── Fungsi utama unduh ───────────────────────────────────────────────────────
def download_video(yt_dlp, url, resolution, output_dir="."):
    res_info = RESOLUTIONS[resolution]

    print(f"\n🎬 Mulai mengunduh...")
    print(f"   Kualitas : {res_info['label']}")
    print(f"   Simpan ke: {os.path.abspath(output_dir)}")
    print()

    ydl_opts = {
        "format": res_info["format"],
        "outtmpl": os.path.join(output_dir, "%(title)s [%(height)sp].%(ext)s"),
        "merge_output_format": "mp4",
        "progress_hooks": [progress_hook],
        "quiet": False,
        "no_warnings": True,
        "postprocessors": [{
            "key": "FFmpegVideoConvertor",
            "preferedformat": "mp4",
        }],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        print(f"\n✅ Berhasil! File MP4 tersimpan di: {os.path.abspath(output_dir)}")
        return True
    except Exception as e:
        print(f"\n❌ Gagal mengunduh: {e}")
        print("   Pastikan link YouTube valid dan koneksi internet stabil.")
        return False

# ─── Menu interaktif ──────────────────────────────────────────────────────────
def interactive_menu(yt_dlp):
    print("=" * 55)
    print("        🎬  YouTube → MP4 Downloader")
    print("=" * 55)
    print("  Mudah dipakai • Otomatis pilih kualitas terbaik")
    print("=" * 55)

    # Input URL
    while True:
        print()
        url = input("📋 Tempel link YouTube di sini:\n   → ").strip()
        if not url:
            print("   ⚠️  Link tidak boleh kosong. Coba lagi.")
            continue
        if not is_valid_youtube_url(url):
            print("   ⚠️  Link tidak valid. Harus berupa link YouTube.")
            print("   Contoh: https://www.youtube.com/watch?v=xxxxx")
            continue
        break

    # Deteksi resolusi terbaik
    best_res, title = detect_best_resolution(yt_dlp, url)
    print(f"\n  🎥 Video  : {title[:60]}{'...' if len(title) > 60 else ''}")
    print(f"  ✨ Kualitas terbaik terdeteksi: {RESOLUTIONS[best_res]['label']}")

    # Pilih resolusi
    print()
    print("  Pilih kualitas video:")
    print("  ─────────────────────────────────────────────")
    for i, (key, val) in enumerate(RESOLUTIONS.items(), 1):
        marker = " ← Terbaik ✨" if key == best_res else ""
        print(f"  [{i}] {val['label']}{marker}")
    print(f"  [5] Gunakan yang terbaik otomatis ({RESOLUTIONS[best_res]['label']})")
    print("  ─────────────────────────────────────────────")

    while True:
        pilihan = input(f"\n  Pilihan Anda [tekan Enter untuk otomatis]: ").strip()

        if pilihan == "" or pilihan == "5":
            resolution = best_res
            break
        elif pilihan in ["1", "2", "3", "4"]:
            resolution = list(RESOLUTIONS.keys())[int(pilihan) - 1]
            break
        else:
            print("  ⚠️  Masukkan angka 1-5.")

    print(f"\n  ✅ Dipilih: {RESOLUTIONS[resolution]['label']}")

    # Folder simpan
    print()
    default_dir = os.path.join(os.path.expanduser("~"), "Downloads")
    folder = input(f"📁 Simpan ke folder mana?\n   [Enter = {default_dir}]\n   → ").strip()

    if not folder:
        folder = default_dir

    if not os.path.exists(folder):
        try:
            os.makedirs(folder)
            print(f"   📁 Folder dibuat: {folder}")
        except Exception as e:
            print(f"   ⚠️  Gagal buat folder: {e}. Simpan di folder saat ini.")
            folder = "."

    # Unduh
    success = download_video(yt_dlp, url, resolution, folder)

    if success:
        print()
        print("=" * 55)
        print("  🎉 Selesai! Video sudah tersimpan sebagai MP4.")
        print(f"  📂 Lokasi: {os.path.abspath(folder)}")
        print("=" * 55)

    # Unduh lagi?
    print()
    lagi = input("  Unduh video lain? [y/tidak]: ").strip().lower()
    if lagi in ["y", "ya", "yes"]:
        interactive_menu(yt_dlp)
    else:
        print("\n  👋 Terima kasih! Sampai jumpa.\n")

# ─── Entry point ─────────────────────────────────────────────────────────────
def main():
    yt_dlp = ensure_ytdlp()

    # Mode argumen langsung
    if len(sys.argv) >= 2:
        url = sys.argv[1]
        resolution = sys.argv[3] if len(sys.argv) >= 4 and sys.argv[2] == "--res" else None

        if not is_valid_youtube_url(url):
            print(f"❌ URL tidak valid: {url}")
            sys.exit(1)

        if not resolution:
            resolution, title = detect_best_resolution(yt_dlp, url)
            print(f"  ✨ Kualitas terbaik: {RESOLUTIONS[resolution]['label']}")
        elif resolution not in RESOLUTIONS:
            print(f"❌ Resolusi tidak valid. Pilih: {', '.join(RESOLUTIONS.keys())}")
            sys.exit(1)

        download_video(yt_dlp, url, resolution)
    else:
        # Mode interaktif
        interactive_menu(yt_dlp)

if __name__ == "__main__":
    main()