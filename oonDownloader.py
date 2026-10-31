import os
import sys
import subprocess
import customtkinter as ctk
from tkinter import filedialog, messagebox
import tkinter as tk
import threading
import re
import json
import shutil
import ssl
import urllib.error
import urllib.request
from datetime import datetime

try:
    import certifi
except ImportError:
    certifi = None

ctk.set_appearance_mode("dark")


def get_ffmpeg_path():
    # PyInstaller temp
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, "ffmpeg.exe")
    return shutil.which("ffmpeg") or "ffmpeg"


YTDLP_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"


def get_data_dir():
    #  %APPDATA%\oonDownloader  for data
    base = os.getenv("APPDATA") or os.path.expanduser("~")
    folder = os.path.join(base, "oonDownloader")
    try:
        os.makedirs(folder, exist_ok=True)
    except OSError:
        pass
    return folder


def get_history_path():
    return os.path.join(get_data_dir(), "history.json")


def get_managed_ytdlp_path():
    # self download and update for yt-dlp.exe
    return os.path.join(get_data_dir(), "yt-dlp.exe")


def get_ytdlp_path():
    managed = get_managed_ytdlp_path()
    if os.path.exists(managed):
        return managed

    if getattr(sys, 'frozen', False):
        app_dir = os.path.dirname(sys.executable)
    else:
        app_dir = os.path.dirname(os.path.abspath(__file__))

    local_ytdlp = os.path.join(app_dir, "yt-dlp.exe")
    if os.path.exists(local_ytdlp):
        return local_ytdlp
    return shutil.which("yt-dlp")


def open_url(req):

    try:
        return urllib.request.urlopen(req, timeout=30)
    except urllib.error.URLError as e:
        if isinstance(e.reason, ssl.SSLCertVerificationError) and certifi:
            ctx = ssl.create_default_context(cafile=certifi.where())
            return urllib.request.urlopen(req, timeout=30, context=ctx)
        raise


def download_ytdlp(progress_cb=None):
    dest = get_managed_ytdlp_path()
    tmp = os.path.join(os.path.dirname(dest), "yt-dlp.new.exe")
    req = urllib.request.Request(
        YTDLP_URL, headers={"User-Agent": "oonDownloader"})
    try:
        with open_url(req) as resp, open(tmp, "wb") as f:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if progress_cb and total:
                    progress_cb(done / total)
        if total and done != total:
            raise RuntimeError("Download was incomplete.")

        res = subprocess.run(
            [tmp, "--version"],
            capture_output=True,
            text=True,
            timeout=60,
            stdin=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        if res.returncode != 0:
            raise RuntimeError(
                "The downloaded yt-dlp.exe could not be started.")
        os.replace(tmp, dest)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    return dest


def get_icon_path():
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, "icon.ico")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")


def load_history():
    path = get_history_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return []
    except json.JSONDecodeError:
        try:
            os.replace(path, path + ".bad")
        except OSError:
            pass
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def save_history(history):
    path = get_history_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def create_db():
    if not os.path.exists(get_history_path()):
        save_history([])


def get_stats():
    try:
        history = load_history()
    except Exception:
        history = []

    total = 0
    counts = {}
    for item in history:
        size = item.get("size_bytes") or 0
        mode = item.get("mode") or "?"
        total += size
        count, mode_size = counts.get(mode, (0, 0))
        counts[mode] = (count + 1, mode_size + size)

    modes = [(mode, count, size)
             for mode, (count, size) in sorted(counts.items())]
    recent = [(item.get("date") or "", item.get("title") or "",
               item.get("mode") or "", item.get("size_bytes") or 0)
              for item in reversed(history[-200:])]
    return {
        "total_bytes": total,
        "modes": modes,
        "history": recent,
    }


def format_size(num_bytes):
    for unit in ["B", "KB", "MB", "GB"]:
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} TB"


def insert_download(title, mode, size_bytes):
    history = load_history()
    history.append({
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "title": title,
        "mode": mode,
        "size_bytes": size_bytes,
    })
    save_history(history)


class Downloader(ctk.CTk):
    def __init__(self, fg_color=None, **kwargs):
        super().__init__(fg_color, **kwargs)
        self.title("oonDownloader")

        try:
            create_db()
        except Exception:
            pass

        try:
            self.iconbitmap(get_icon_path())
        except Exception:
            pass

        self.resizable(False, False)
        self.configure(fg_color="#000000")

        app_width = 600
        app_height = 275
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()

        center_screen_x = int((screen_width/2)-(app_width/2))
        center_screen_y = int((screen_height/2)-(app_height/2))
        self.geometry(
            f"{app_width}x{app_height}+{center_screen_x}+{center_screen_y}")

        self.download_location = os.path.join(
            os.path.expanduser('~'), "Downloads")
        self.active_mode = "MP4"
        self.settings_visible = False
        self.stats_visible = False

        ascii_text = r"""
                         ___                    _                 _
     ___   ___  _ __    /   \_____      ___ __ | | ___   __ _  __| | ___ _ __
    / _ \ / _ \| '_ \  / /\ / _ \ \ /\ / / '_ \| |/ _ \ / _` |/ _` |/ _ \ '__|
   | (_) | (_) | | | |/ /_// (_) \ V  V /| | | | | (_) | (_| | (_| |  __/ |
    \___/ \___/|_| |_/___,' \___/ \_/\_/ |_| |_|_|\___/ \__,_|\__,_|\___|_|
                                                                       """
        self.ascii_label = ctk.CTkLabel(self, text=ascii_text, font=(
            "Courier New", 11, "bold"), text_color="#00FF41", justify="left")
        self.ascii_label.pack(pady=(0, 20))

        self.input_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.input_frame.pack(pady=10, padx=50, fill="x")

        self.url_entry = ctk.CTkEntry(
            self.input_frame,
            placeholder_text="Enter YouTube Link Here",
            height=45,
            fg_color="#000000",
            text_color="#ffffff",
            border_color="#333333",
            border_width=2,
            font=("Courier New", 14),
            corner_radius=4
        )
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.url_entry.bind("<Button-3>", self.show_context_menu)

        self.context_menu = tk.Menu(
            self, tearoff=0,
            bg="#222222", fg="#ffffff",
            activebackground="#333333", activeforeground="#ffffff",
            font=("Courier New", 8, "bold"),
            relief="flat", bd=0, activeborderwidth=0
        )
        self.context_menu.add_command(
            label="Cut", command=lambda: self.url_entry._entry.event_generate("<<Cut>>"))
        self.context_menu.add_command(
            label="Copy", command=lambda: self.url_entry._entry.event_generate("<<Copy>>"))
        self.context_menu.add_command(
            label="Paste", command=self.paste_url)

        self.start_btn = ctk.CTkButton(
            self.input_frame,
            text=">",
            width=50,
            height=45,
            fg_color="#ffffff",
            text_color="#000000",
            hover_color="#cccccc",
            font=("Arial", 20, "bold"),
            corner_radius=4,
            command=self.download_thread_start
        )
        self.start_btn.pack(side="right")

        self.controls_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.controls_frame.pack(anchor="w", padx=50, pady=10)

        self.paste_btn = ctk.CTkButton(
            self.input_frame,
            text="Paste",
            width=60,
            height=45,
            fg_color="#222222",
            text_color="#ffffff",
            hover_color="#333333",
            corner_radius=4,
            font=("Courier New", 14),
            command=self.paste_url
        )
        self.paste_btn.pack(side="right", padx=(0, 10))

        self.settings_btn = ctk.CTkButton(
            self.controls_frame,
            text="Settings",
            width=100,
            fg_color="#222222",
            text_color="#ffffff",
            hover_color="#333333",
            corner_radius=4,
            font=("Courier New", 14),
            command=self.open_settings
        )
        self.settings_btn.pack(side="left", padx=(0, 15))

        self.stats_btn = ctk.CTkButton(
            self.controls_frame,
            text="Stats",
            width=100,
            fg_color="#222222",
            text_color="#ffffff",
            hover_color="#333333",
            corner_radius=4,
            font=("Courier New", 14),
            command=self.open_stats
        )
        self.stats_btn.pack(side="left", padx=(0, 15))

        self.mp3_mode_btn = ctk.CTkButton(
            self.controls_frame,
            text="mp3",
            width=80,
            fg_color="#222222",
            text_color="#ffffff",
            corner_radius=4,
            font=("Courier New", 14),
            command=lambda: self.switch_mode("MP3")
        )
        self.mp3_mode_btn.pack(side="left", padx=(0, 15))

        self.mp4_mode_btn = ctk.CTkButton(
            self.controls_frame,
            text="mp4",
            width=80,
            fg_color="#ffffff",
            text_color="#000000",
            corner_radius=4,
            font=("Courier New", 14),
            command=lambda: self.switch_mode("MP4")
        )
        self.mp4_mode_btn.pack(side="left")

        self.mp3_var = ctk.StringVar(value="320kbps (mp3)")
        self.mp4_var = ctk.StringVar(value="1080p")

        self.settings_panel = ctk.CTkFrame(
            self, fg_color="#0a0a0a", border_color="#222222", border_width=1, corner_radius=6)

        self.stats_panel = ctk.CTkFrame(
            self, height=202, fg_color="#0a0a0a", border_color="#222222", border_width=1, corner_radius=6)
        self.stats_panel.pack_propagate(False)

        self.stats_label = ctk.CTkLabel(
            self.stats_panel, text="", font=("Courier New", 12, "bold"),
            text_color="#ffffff", anchor="w", justify="left")
        self.stats_label.pack(anchor="w", padx=20, pady=(10, 4))

        self.history_box = ctk.CTkTextbox(
            self.stats_panel, height=85, fg_color="#0a0a0a",
            text_color="#ffffff", font=("Courier New", 12, "bold"),
            border_width=0, wrap="none",
            scrollbar_button_color="#333333", scrollbar_button_hover_color="#555555")
        self.history_box.pack(fill="both", expand=True, padx=15, pady=(0, 10))
        self.history_box.configure(state="disabled")

        label = ctk.CTkLabel(self.settings_panel, text="Download Location", font=(
            "Courier New", 12, "bold"), text_color="#ffffff")
        label.pack(anchor="w", padx=20, pady=(10, 2))

        loc_frame = ctk.CTkFrame(self.settings_panel, fg_color="transparent")
        loc_frame.pack(fill="x", padx=20, pady=5)

        self.path_entry = ctk.CTkEntry(
            loc_frame, fg_color="#000000", border_color="#333333")
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.path_entry.insert(0, self.download_location)
        self.path_entry.configure(state="disabled")

        choice_btn = ctk.CTkButton(
            loc_frame, text="...", width=40, fg_color="#ffffff", text_color="#000000",
            hover_color="#cccccc", command=self.change_location
        )
        choice_btn.pack(side="right")

        menus_frame = ctk.CTkFrame(self.settings_panel, fg_color="transparent")
        menus_frame.pack(fill="x", padx=20, pady=(5, 5))

        mp3_sub_frame = ctk.CTkFrame(menus_frame, fg_color="transparent")
        mp3_sub_frame.pack(side="left", fill="x", expand=True, padx=(0, 10))
        ctk.CTkLabel(mp3_sub_frame, text="mp3 quality:", font=(
            "Courier New", 11), text_color="#ffffff").pack(anchor="w")
        self.mp3_menu = ctk.CTkOptionMenu(
            mp3_sub_frame, values=[
                "320kbps (mp3)", "192kbps (mp3)", "128kbps (mp3)"],
            variable=self.mp3_var, fg_color="#222222", button_color="#333333", corner_radius=4
        )
        self.mp3_menu.pack(fill="x", pady=2)

        mp4_sub_frame = ctk.CTkFrame(menus_frame, fg_color="transparent")
        mp4_sub_frame.pack(side="right", fill="x", expand=True)
        ctk.CTkLabel(mp4_sub_frame, text="mp4 quality:", font=(
            "Courier New", 11), text_color="#ffffff").pack(anchor="w")
        self.mp4_menu = ctk.CTkOptionMenu(
            mp4_sub_frame, values=[
                "2160p (4K)", "1440p", "1080p", "720p", "480p"],
            variable=self.mp4_var, fg_color="#222222", button_color="#333333", corner_radius=4
        )
        self.mp4_menu.pack(fill="x", pady=2)

        self.update_btn = ctk.CTkButton(
            self.settings_panel,
            text="Update yt-dlp",
            height=30,
            fg_color="#1a1a1a",
            hover_color="#333333",
            text_color="#00FF41",
            font=("Courier New", 11, "bold"),
            corner_radius=4,
            command=self.update_yt_dlp
        )
        self.update_btn.pack(pady=(5, 20), padx=20, fill="x")

        self.status_label = ctk.CTkLabel(self, text="", font=(
            "Courier New", 12), text_color="#ffffff")
        self.progress_bar = ctk.CTkProgressBar(
            self, width=500, fg_color="#111111", progress_color="#ffffff", corner_radius=2)
        self.progress_bar.set(0)

    def show_update_progress(self, fraction):
        self.update_btn.configure(
            text=f"Downloading... {int(fraction * 100)}%")

    def show_ytdlp_progress(self, fraction):
        self.progress_bar.set(fraction)
        self.status_label.configure(
            text=f"Downloading yt-dlp... {int(fraction * 100)}%")

    def update_yt_dlp(self):
        def run_update():
            self.update_btn.configure(text="Updating...", state="disabled")
            managed = get_managed_ytdlp_path()
            msg = ""
            try:
                updated = False
                if os.path.exists(managed):
                    res = subprocess.run(
                        [managed, "-U"],
                        capture_output=True,
                        text=True,
                        stdin=subprocess.DEVNULL,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                    )
                    if res.returncode == 0:
                        msg = res.stdout.strip() if res.stdout else "yt-dlp is up to date."
                        updated = True

                if not updated:
                    # Henüz kopya yok ya da -U başarısız oldu: temiz bir kopya indir
                    download_ytdlp(self.show_update_progress)
                    msg = "yt-dlp downloaded."
            except Exception as e:
                self.update_btn.configure(text="Update yt-dlp", state="normal")
                messagebox.showerror("Error", f"Update failed:\n{e}")
                return

            self.update_btn.configure(text="Update yt-dlp", state="normal")
            messagebox.showinfo("Update", msg)

        threading.Thread(target=run_update, daemon=True).start()

    def paste_url(self):
        try:
            text = self.clipboard_get().strip()
        except tk.TclError:
            return
        self.url_entry.delete(0, "end")
        self.url_entry.insert(0, text)

    def switch_mode(self, mode):
        self.active_mode = mode
        if mode == "MP4":
            self.mp4_mode_btn.configure(
                fg_color="#ffffff", text_color="#000000")
            self.mp3_mode_btn.configure(
                fg_color="#222222", text_color="#ffffff")
        else:
            self.mp3_mode_btn.configure(
                fg_color="#ffffff", text_color="#000000")
            self.mp4_mode_btn.configure(
                fg_color="#222222", text_color="#ffffff")

    def open_settings(self):
        if not self.settings_visible:
            if self.stats_visible:
                self.close_stats()
            self.geometry("600x475")
            self.settings_panel.pack(fill="x", padx=50, pady=10)
            self.settings_btn.configure(
                fg_color="#ffffff", text_color="#000000")
            self.settings_visible = True
        else:
            self.settings_panel.pack_forget()
            self.settings_btn.configure(
                fg_color="#222222", text_color="#ffffff")
            self.geometry("600x275")
            self.settings_visible = False

    def open_stats(self):
        if not self.stats_visible:
            if self.settings_visible:
                self.settings_panel.pack_forget()
                self.settings_btn.configure(
                    fg_color="#222222", text_color="#ffffff")
                self.settings_visible = False
            self.refresh_stats()
            self.geometry("600x475")
            self.stats_panel.pack(fill="x", padx=50, pady=10)
            self.stats_btn.configure(fg_color="#ffffff", text_color="#000000")
            self.stats_visible = True
        else:
            self.close_stats()
            self.geometry("600x275")

    def close_stats(self):
        self.stats_panel.pack_forget()
        self.stats_btn.configure(fg_color="#222222", text_color="#ffffff")
        self.stats_visible = False

    def refresh_stats(self):
        stats = get_stats()

        self.history_box.configure(state="normal")
        self.history_box.delete("1.0", "end")

        if not stats["modes"]:
            self.history_box.configure(state="disabled")
            self.stats_label.configure(text="No downloads yet.")
            return 1

        lines = [f"Total downloaded: {format_size(stats['total_bytes'])}"]

        for mode, count, size in stats["modes"]:
            lines.append(f"{mode}: {count} files, {format_size(size)}")

        lines.append("Recent downloads:")

        title_w = 34
        for date, title, mode, size in stats["history"]:
            short = title if len(
                title) <= title_w else title[:title_w - 3] + "..."
            self.history_box.insert(
                "end",
                f"{date[:10]} {mode} {short.ljust(title_w)} {format_size(size).rjust(9)}\n")

        self.history_box.configure(state="disabled")
        self.stats_label.configure(text="\n".join(lines))
        return len(lines)

    def show_context_menu(self, event):
        self.url_entry.focus_set()
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def change_location(self):
        chosen_location = filedialog.askdirectory()
        if chosen_location:
            self.download_location = chosen_location
            self.path_entry.configure(state="normal")
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, chosen_location)
            self.path_entry.configure(state="disabled")

    def download_process(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning(
                "Warning", "Please enter a valid URL address")
            self.interface_status(active=True)
            return
        if "/playlist?" in url or "/@" in url or "/channel/" in url:
            messagebox.showwarning(
                "Warning", "Playlist links are not supported. Use a single video link.")
            self.interface_status(active=True)
            return
        ytdlp_bin = get_ytdlp_path()
        if ytdlp_bin is None:
            try:
                self.status_label.configure(text="Downloading yt-dlp...")
                ytdlp_bin = download_ytdlp(self.show_ytdlp_progress)
                self.progress_bar.set(0)
            except Exception as e:
                messagebox.showerror(
                    "Error", f"Could not download yt-dlp:\n{e}")
                self.interface_status(active=True)
                return
        ffmpeg_bin = get_ffmpeg_path()
        out_pattern = os.path.join(self.download_location, "%(title)s.%(ext)s")

        cmd = [
            ytdlp_bin,
            url,
            "-o", out_pattern,
            "--ffmpeg-location", ffmpeg_bin,
            "--newline",
            "--no-playlist",
            "--no-quiet",
            "--encoding",
            "utf-8",
            "--print", "after_move:TITLE::%(title)s",
            "--print", "after_move:PATH::%(filepath)s"
        ]

        if self.active_mode == "MP3":
            quality_n = self.mp3_var.get().split("k")[0]
            cmd.extend([
                "-x",
                "--audio-format", "mp3",
                "--audio-quality", quality_n,
                "--embed-thumbnail",
                "--convert-thumbnails", "jpg"
            ])
        else:
            resolution = self.mp4_var.get().split("p")[0]
            cmd.extend([
                "-f", f"bestvideo[height<={resolution}]+bestaudio/best",
                "--merge-output-format", "mp4"
            ])

        try:
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='ignore',
                bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            current_progress = 0.0
            phase = 1  # 1: Video (veya MP3), 2: Ses
            last_raw_percent = 0.0

            title = ""
            file_path = ""

            for line in iter(process.stdout.readline, ''):
                if not line:
                    break
                line = line.strip()
                if line.startswith("TITLE::"):
                    title = line[len("TITLE::"):]
                elif line.startswith("PATH::"):
                    file_path = line[len("PATH::"):]
                elif '[download]' in line and '%' in line:
                    match_percent = re.search(r'(\d+\.\d+|\d+)%', line)
                    match_speed = re.search(r'at\s+([0-9\.]+\s*\w+/s)', line)

                    if match_percent:
                        raw_p = float(match_percent.group(1))
                        speed_str = match_speed.group(1) if match_speed else ""

                        # 1. SAHTE %100 KORUMASI
                        is_small_file = any(
                            unit in line for unit in ['KiB', ' B ', 'bytes'])
                        if raw_p == 100.0 and (is_small_file or last_raw_percent < 50.0):
                            continue

                        # 2. FAZ GEÇİŞİ (Video bitti, Ses başladı)
                        if self.active_mode == "MP4" and phase == 1:
                            if last_raw_percent > 50.0 and raw_p < 20.0:
                                phase = 2
                                last_raw_percent = 0.0

                        last_raw_percent = max(last_raw_percent, raw_p)

                        # 3. BAR VE YÜZDE HESAPLAMA
                        if self.active_mode == "MP4":
                            if phase == 1:
                                target_p = (raw_p / 100.0) * 0.75
                                phase_prefix = "Downloading Video"
                            else:
                                target_p = 0.75 + ((raw_p / 100.0) * 0.20)
                                phase_prefix = "Downloading Audio"
                        else:
                            target_p = (raw_p / 100.0) * 0.90
                            phase_prefix = "Downloading Audio"

                        if target_p > current_progress:
                            current_progress = target_p

                        display_percent = current_progress * 100
                        status_msg = f"{phase_prefix}: %{display_percent:.1f}"
                        if speed_str:
                            status_msg += f" ({speed_str})"

                        self.progress_bar.set(current_progress)
                        self.status_label.configure(text=status_msg)
                        self.update_idletasks()

                elif any(kw in line for kw in ['[ExtractAudio]', '[ThumbnailsConvertor]', '[EmbedThumbnail]', '[Merger]']):
                    current_progress = max(current_progress, 0.95)
                    display_percent = current_progress * 100
                    self.progress_bar.set(current_progress)

                    if self.active_mode == "MP3":
                        self.status_label.configure(
                            text=f"Converting & Embedding Cover... %{display_percent:.1f} 🎧")
                    else:
                        self.status_label.configure(
                            text=f"Merging Video & Audio... %{display_percent:.1f} 🎬")
                    self.update_idletasks()

            process.stdout.close()
            process.wait()
            if process.returncode == 0:
                self.progress_bar.set(1.0)
                self.status_label.configure(text="Completed %100.0 ✨")
                status = "success"
            else:
                messagebox.showerror(
                    "Error", "Download failed. Check the URL or connection.")
                status = "error"
            size_bytes = 0
            if file_path and os.path.exists(file_path):
                size_bytes = os.path.getsize(file_path)
            if status == "success":
                try:
                    insert_download(title, self.active_mode, size_bytes)
                except Exception:
                    pass

        except Exception as e:
            messagebox.showerror("Error", f"There was a problem:\n{e}")
        finally:
            self.interface_status(active=True)

    def interface_status(self, active):
        if not active:
            if self.settings_visible:
                self.open_settings()
            if self.stats_visible:
                self.close_stats()

            self.geometry("600x380")

            self.settings_btn.configure(
                state="disabled", fg_color="#111111", text_color="#555555")
            self.stats_btn.configure(
                state="disabled", fg_color="#111111", text_color="#555555")
            self.mp3_mode_btn.configure(
                state="disabled", fg_color="#111111", text_color="#555555")
            self.mp4_mode_btn.configure(
                state="disabled", fg_color="#111111", text_color="#555555")
            self.start_btn.configure(state="disabled", fg_color="#222222")

            self.status_label.pack(pady=(15, 5))
            self.progress_bar.pack(pady=5)
            self.status_label.configure(text="Connecting...")
        else:

            self.settings_btn.configure(
                state="normal", fg_color="#222222", text_color="#ffffff")
            self.stats_btn.configure(
                state="normal", fg_color="#222222", text_color="#ffffff")
            self.start_btn.configure(state="normal", fg_color="#ffffff")
            self.switch_mode(self.active_mode)
            self.mp3_mode_btn.configure(state="normal")
            self.mp4_mode_btn.configure(state="normal")
            self.status_label.pack_forget()
            self.progress_bar.pack_forget()
            self.progress_bar.set(0)
            self.geometry("600x275")

    def download_thread_start(self):
        self.interface_status(active=False)
        threading.Thread(target=self.download_process, daemon=True).start()


if __name__ == "__main__":
    app = Downloader()
    app.mainloop()
