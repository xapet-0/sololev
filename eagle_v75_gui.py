import logging
import os
import re
import threading
import time
import webbrowser
from dataclasses import dataclass
from io import BytesIO
from queue import Queue, Empty
from tkinter import filedialog, messagebox
from urllib.request import urlopen

import customtkinter as ctk
from PIL import Image
import yt_dlp

APP_TITLE = "RT57 霊桜 Studio"
APP_TAGLINE = "Studio-grade video intelligence with sakura energy and clean focus."
DOWNLOAD_DIR = "my_videos"
LOG_DIR = "logs"
LOG_FILE = "rt57_rei_sakura.log"
VIDEO_EXTENSIONS = (".mp4", ".mkv", ".webm", ".flv", ".avi")
DEFAULT_LANG_PRIORITY = ["ja", "ko", "pl", "ru", "zh-Hans", "zh-Hant", "en", "ar"]
PREFERRED_LANGS = ["ja", "ko", "pl", "ru", "zh-Hans", "zh-Hant"]
ACCENT_COLOR = "#ff7ac1"
ACCENT_SOFT = "#3ee6b6"
PANEL_BG = "#141820"
CANVAS_BG = "#0b0f14"
TEXT_DARK = "#eef2f7"
TEXT_MUTED = "#92a0b3"
CARD_BG = "#11161e"
LOGO_GLYPH = "🌸🜂"
FONT_FAMILY = "Roboto"


@dataclass
class VideoInfo:
    url: str
    title: str = ""
    uploader: str = ""
    duration: int = 0
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    webpage_url: str = ""
    thumbnail: str = ""
    description: str = ""
    tags: list[str] | None = None


class EagleV75App:
    def __init__(self, root: ctk.CTk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1040x720")
        self.root.minsize(980, 680)
        self.root.configure(bg=CANVAS_BG)
        self.queue: Queue[str] = Queue()
        self.current_info: VideoInfo | None = None
        self._setup_logging()
        self._ensure_directory()
        self._build_style()
        self._build_ui()
        self._refresh_video_list()
        self._poll_queue()

    def _ensure_directory(self) -> None:
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        os.makedirs(LOG_DIR, exist_ok=True)

    def _setup_logging(self) -> None:
        os.makedirs(LOG_DIR, exist_ok=True)
        log_path = os.path.join(LOG_DIR, LOG_FILE)
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(message)s",
            handlers=[logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler()],
        )
        logging.info("RT57 霊桜 Studio session started.")

    def _build_style(self) -> None:
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("dark-blue")
        self.root.configure(fg_color=CANVAS_BG)

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self.root, fg_color=CANVAS_BG)
        header.grid(row=0, column=0, sticky="ew", padx=28, pady=(20, 12))
        header.columnconfigure(0, weight=1)

        branding = ctk.CTkFrame(header, fg_color="transparent")
        branding.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            branding,
            text=LOGO_GLYPH,
            text_color=ACCENT_COLOR,
            font=(FONT_FAMILY, 26, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            branding,
            text=APP_TITLE,
            text_color=TEXT_DARK,
            font=(FONT_FAMILY, 24, "bold"),
        ).grid(row=0, column=1, sticky="w", padx=(8, 0))
        ctk.CTkLabel(
            header,
            text=APP_TAGLINE,
            text_color=TEXT_MUTED,
            font=(FONT_FAMILY, 12),
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        body = ctk.CTkFrame(self.root, fg_color=CANVAS_BG)
        body.grid(row=1, column=0, sticky="nsew", padx=24, pady=10)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        self.tabview = ctk.CTkTabview(body, fg_color=CANVAS_BG, segmented_button_selected_color=ACCENT_COLOR)
        self.tabview.grid(row=0, column=0, sticky="nsew")
        dashboard_tab = self.tabview.add("Dashboard")
        subtitles_tab = self.tabview.add("Subtitles")
        intel_tab = self.tabview.add("Intelligence")

        self.url_var = ctk.StringVar()
        self.lang_var = ctk.StringVar(value=DEFAULT_LANG_PRIORITY[0])
        self.status_var = ctk.StringVar(value="Ready for capture.")
        self.subtitle_font_size = ctk.IntVar(value=11)
        self.subtitle_wrap = ctk.BooleanVar(value=True)
        self.lang_display_map: dict[str, tuple[str, str]] = {}
        self.thumbnail_image: ctk.CTkImage | None = None
        self.current_title = ""
        self.subtitle_title_var = ctk.StringVar(value="Title: —")
        self.subtitle_lines_var = ctk.StringVar(value="Subtitle lines: —")
        self.subtitle_desc_var = ctk.StringVar(value="Description: —")

        dashboard_tab.columnconfigure(0, weight=1)
        dashboard_tab.rowconfigure(1, weight=1)

        preview_card = self._create_card(dashboard_tab, "Video Preview")
        self.thumbnail_label = ctk.CTkLabel(
            preview_card,
            text="No thumbnail yet.",
            text_color=TEXT_MUTED,
            width=360,
            height=200,
            fg_color=PANEL_BG,
            corner_radius=12,
        )
        self.thumbnail_label.pack(padx=12, pady=(0, 12))

        link_card = self._create_card(dashboard_tab, "Link & Controls")
        ctk.CTkLabel(link_card, text="YouTube URL", text_color=TEXT_MUTED, font=(FONT_FAMILY, 12)).pack(
            anchor="w", padx=12, pady=(12, 4)
        )
        self.url_entry = ctk.CTkEntry(
            link_card,
            textvariable=self.url_var,
            corner_radius=10,
            fg_color=PANEL_BG,
            text_color=TEXT_DARK,
        )
        self.url_entry.pack(fill="x", padx=12, pady=(0, 8))

        action_row = ctk.CTkFrame(link_card, fg_color="transparent")
        action_row.pack(fill="x", padx=12, pady=(0, 12))
        self._button(action_row, "Analyze Link", self._fetch_info).pack(side="left")
        self._button(action_row, "Open YouTube", self._open_in_browser, secondary=True).pack(
            side="left", padx=(8, 0)
        )

        download_row = ctk.CTkFrame(link_card, fg_color="transparent")
        download_row.pack(fill="x", padx=12, pady=(0, 12))
        self._button(download_row, "Download Video", self._download_video).pack(side="left")
        self._button(download_row, "Download Audio", self._download_audio, secondary=True).pack(
            side="left", padx=(8, 0)
        )
        self._button(download_row, "Open Folder", self._open_download_dir, secondary=True).pack(
            side="left", padx=(8, 0)
        )

        info_card = self._create_card(dashboard_tab, "Video Snapshot")
        self.info_text = ctk.CTkTextbox(
            info_card,
            height=160,
            fg_color=PANEL_BG,
            text_color=TEXT_DARK,
            font=(FONT_FAMILY, 11),
        )
        self.info_text.pack(fill="both", padx=12, pady=(0, 12))
        self.info_text.configure(state="disabled")

        performance_card = self._create_card(dashboard_tab, "Download Telemetry")
        self.progress_bar = ctk.CTkProgressBar(
            performance_card, progress_color=ACCENT_COLOR, fg_color=PANEL_BG
        )
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", padx=12, pady=(0, 8))

        self.speed_var = ctk.StringVar(value="Speed: —")
        self.eta_var = ctk.StringVar(value="ETA: —")
        self.size_var = ctk.StringVar(value="Size: —")
        metrics = ctk.CTkFrame(performance_card, fg_color="transparent")
        metrics.pack(fill="x", padx=12, pady=(0, 12))
        ctk.CTkLabel(metrics, textvariable=self.speed_var, text_color=TEXT_MUTED).pack(anchor="w")
        ctk.CTkLabel(metrics, textvariable=self.eta_var, text_color=TEXT_MUTED).pack(anchor="w")
        ctk.CTkLabel(metrics, textvariable=self.size_var, text_color=TEXT_MUTED).pack(anchor="w")

        library_card = self._create_card(dashboard_tab, "Local Library")
        self.video_list_frame = ctk.CTkScrollableFrame(
            library_card, fg_color=PANEL_BG, scrollbar_button_color=ACCENT_COLOR, height=180
        )
        self.video_list_frame.pack(fill="both", padx=12, pady=(0, 12))

        subtitles_tab.columnconfigure(0, weight=1)
        subtitles_card = self._create_card(subtitles_tab, "Subtitle Studio")
        subtitle_meta = ctk.CTkFrame(subtitles_card, fg_color="transparent")
        subtitle_meta.pack(fill="x", padx=12, pady=(12, 8))
        ctk.CTkLabel(subtitle_meta, textvariable=self.subtitle_title_var, text_color=TEXT_MUTED).pack(
            anchor="w"
        )
        ctk.CTkLabel(subtitle_meta, textvariable=self.subtitle_lines_var, text_color=TEXT_MUTED).pack(
            anchor="w"
        )
        ctk.CTkLabel(subtitle_meta, textvariable=self.subtitle_desc_var, text_color=TEXT_MUTED).pack(
            anchor="w"
        )
        lang_row = ctk.CTkFrame(subtitles_card, fg_color="transparent")
        lang_row.pack(fill="x", padx=12, pady=(12, 8))
        ctk.CTkLabel(lang_row, text="Language", text_color=TEXT_MUTED).pack(side="left")
        self.lang_combo = ctk.CTkComboBox(
            lang_row,
            values=DEFAULT_LANG_PRIORITY,
            variable=self.lang_var,
            fg_color=PANEL_BG,
            border_color=ACCENT_SOFT,
            button_color=ACCENT_COLOR,
            button_hover_color=ACCENT_SOFT,
            dropdown_fg_color=PANEL_BG,
        )
        self.lang_combo.pack(side="left", padx=(8, 0), fill="x", expand=True)
        self._button(lang_row, "Refresh", self._refresh_languages, secondary=True).pack(
            side="left", padx=(8, 0)
        )

        subtitle_actions = ctk.CTkFrame(subtitles_card, fg_color="transparent")
        subtitle_actions.pack(fill="x", padx=12, pady=(0, 8))
        self._button(subtitle_actions, "Fetch subtitles", self._download_subtitles).pack(side="left")
        self._button(subtitle_actions, "Save SRT", self._save_srt_as, secondary=True).pack(
            side="left", padx=(8, 0)
        )
        self._button(subtitle_actions, "Copy subtitles", self._copy_subtitles, secondary=True).pack(
            side="left", padx=(8, 0)
        )

        subtitle_controls = ctk.CTkFrame(subtitles_card, fg_color="transparent")
        subtitle_controls.pack(fill="x", padx=12, pady=(0, 8))
        ctk.CTkLabel(subtitle_controls, text="Font size", text_color=TEXT_MUTED).pack(side="left")
        ctk.CTkSlider(
            subtitle_controls,
            from_=10,
            to=18,
            number_of_steps=8,
            variable=self.subtitle_font_size,
            command=self._set_subtitle_font_size,
        ).pack(side="left", padx=(8, 12), fill="x", expand=True)
        ctk.CTkSwitch(
            subtitle_controls,
            text="Wrap",
            variable=self.subtitle_wrap,
            command=self._toggle_subtitle_wrap,
        ).pack(side="right")

        self.subtitle_text = ctk.CTkTextbox(
            subtitles_card,
            height=260,
            fg_color=PANEL_BG,
            text_color=TEXT_DARK,
            font=(FONT_FAMILY, self.subtitle_font_size.get()),
            wrap="word",
        )
        self.subtitle_text.pack(fill="both", padx=12, pady=(0, 12))

        intel_tab.columnconfigure(0, weight=1)
        intel_card = self._create_card(intel_tab, "Comments & Links")
        intel_actions = ctk.CTkFrame(intel_card, fg_color="transparent")
        intel_actions.pack(fill="x", padx=12, pady=(12, 8))
        self._button(intel_actions, "Fetch comments", self._fetch_comments).pack(side="left")
        self._button(intel_actions, "Extract links", self._extract_links, secondary=True).pack(
            side="left", padx=(8, 0)
        )
        self._button(intel_actions, "Clear", self._clear_comments, secondary=True).pack(
            side="left", padx=(8, 0)
        )

        self.comments_text = ctk.CTkTextbox(
            intel_card,
            height=220,
            fg_color=PANEL_BG,
            text_color=TEXT_DARK,
            font=(FONT_FAMILY, 11),
        )
        self.comments_text.pack(fill="both", padx=12, pady=(0, 12))

        self.links_list_frame = ctk.CTkScrollableFrame(
            intel_card, fg_color=PANEL_BG, scrollbar_button_color=ACCENT_COLOR, height=140
        )
        self.links_list_frame.pack(fill="both", padx=12, pady=(0, 12))

        status_frame = ctk.CTkFrame(self.root, fg_color=CANVAS_BG)
        status_frame.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 18))
        status_frame.columnconfigure(0, weight=1)
        ctk.CTkLabel(status_frame, textvariable=self.status_var, text_color=TEXT_MUTED).grid(
            row=0, column=0, sticky="w"
        )

    def _create_card(self, parent: ctk.CTkBaseClass, title: str) -> ctk.CTkFrame:
        card = ctk.CTkFrame(parent, fg_color=CARD_BG, corner_radius=16)
        card.pack(fill="x", pady=(0, 16))
        ctk.CTkLabel(
            card, text=title, text_color=ACCENT_COLOR, font=(FONT_FAMILY, 14, "bold")
        ).pack(anchor="w", padx=12, pady=(12, 8))
        return card

    def _button(self, parent: ctk.CTkBaseClass, text: str, command, secondary: bool = False) -> ctk.CTkButton:
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            corner_radius=16,
            fg_color=PANEL_BG if secondary else ACCENT_COLOR,
            hover_color=ACCENT_SOFT if secondary else "#ff8fc1",
            text_color=TEXT_DARK,
            font=(FONT_FAMILY, 12, "bold" if not secondary else "normal"),
        )

    def _set_subtitle_font_size(self, value: float) -> None:
        size = int(round(value))
        self.subtitle_font_size.set(size)
        self.subtitle_text.configure(font=(FONT_FAMILY, size))

    def _toggle_subtitle_wrap(self) -> None:
        wrap_mode = "word" if self.subtitle_wrap.get() else "none"
        self.subtitle_text.configure(wrap=wrap_mode)

    def _update_subtitle_meta(self) -> None:
        title = self.current_info.title if self.current_info else "—"
        description = self.current_info.description if self.current_info else ""
        trimmed = " ".join(description.split())[:140] if description else "—"
        self.subtitle_title_var.set(f"Title: {title}")
        self.subtitle_desc_var.set(f"Description: {trimmed}")

    def _update_subtitle_stats(self) -> None:
        content = self.subtitle_text.get("1.0", "end").strip()
        if not content:
            self.subtitle_lines_var.set("Subtitle lines: —")
            return
        lines = [line for line in content.splitlines() if line.strip()]
        self.subtitle_lines_var.set(f"Subtitle lines: {len(lines)}")

    def _clear_comments(self) -> None:
        self.comments_text.delete("1.0", "end")
        for child in self.links_list_frame.winfo_children():
            child.destroy()
        self._set_status("Cleared comments and links.")

    def _render_video_list(self, files: list[str]) -> None:
        for child in self.video_list_frame.winfo_children():
            child.destroy()
        if not files:
            ctk.CTkLabel(
                self.video_list_frame,
                text="No videos downloaded yet.",
                text_color=TEXT_MUTED,
                font=(FONT_FAMILY, 11),
            ).pack(anchor="w", padx=8, pady=6)
            return
        for filename in files:
            ctk.CTkButton(
                self.video_list_frame,
                text=filename,
                command=lambda name=filename: self._select_video(name),
                fg_color="transparent",
                hover_color=ACCENT_SOFT,
                text_color=TEXT_DARK,
                anchor="w",
                corner_radius=12,
            ).pack(fill="x", padx=6, pady=4)

    def _render_links(self, links: list[str]) -> None:
        for child in self.links_list_frame.winfo_children():
            child.destroy()
        if not links:
            ctk.CTkLabel(
                self.links_list_frame,
                text="No links detected.",
                text_color=TEXT_MUTED,
                font=(FONT_FAMILY, 11),
            ).pack(anchor="w", padx=8, pady=6)
            return
        for link in links:
            ctk.CTkButton(
                self.links_list_frame,
                text=link,
                command=lambda url=link: webbrowser.open(url),
                fg_color="transparent",
                hover_color=ACCENT_SOFT,
                text_color=ACCENT_COLOR,
                anchor="w",
                corner_radius=12,
            ).pack(fill="x", padx=6, pady=4)

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)
        self.queue.put(text)
        logging.info(text)

    def _append_info(self, text: str) -> None:
        self.info_text.configure(state="normal")
        self.info_text.delete("1.0", "end")
        self.info_text.insert("end", text)
        self.info_text.configure(state="disabled")

    def _append_subtitles(self, text: str) -> None:
        self.subtitle_text.delete("1.0", "end")
        self.subtitle_text.insert("end", text)
        self._update_subtitle_stats()

    def _append_description(self, text: str) -> None:
        self.description_text.delete("1.0", "end")
        self.description_text.insert("end", text)

    def _append_comments(self, text: str) -> None:
        self.comments_text.delete("1.0", "end")
        self.comments_text.insert("end", text)

    def _fetch_info(self) -> None:
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Heads up", "Please paste a YouTube link first.")
            return
        self._set_status("Analyzing the link...")
        threading.Thread(target=self._fetch_info_worker, args=(url,), daemon=True).start()

    def _fetch_info_worker(self, url: str) -> None:
        ydl_opts = {
            "quiet": True,
            "nocheckcertificate": True,
            "skip_download": True,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            self.current_info = VideoInfo(
                url=url,
                title=info.get("title", ""),
                uploader=info.get("uploader", ""),
                duration=info.get("duration", 0),
                view_count=info.get("view_count", 0),
                like_count=info.get("like_count", 0) or 0,
                comment_count=info.get("comment_count", 0) or 0,
                webpage_url=info.get("webpage_url", url),
                thumbnail=info.get("thumbnail", ""),
                description=info.get("description", "") or "",
                tags=info.get("tags") or [],
            )
            self.current_title = self.current_info.title
            details = self._format_info(self.current_info)
            self.root.after(0, lambda: self._append_info(details))
            self.root.after(0, lambda: self._append_description(self._format_description(self.current_info)))
            self.root.after(0, self._update_subtitle_meta)
            self.root.after(0, lambda: self._apply_language_options(info))
            self._fetch_thumbnail(info.get("thumbnail"))
            self._set_status("Link analyzed successfully.")
        except Exception as exc:
            self._set_status(f"Link analysis failed: {exc}")

    def _format_info(self, info: VideoInfo) -> str:
        duration = time.strftime("%H:%M:%S", time.gmtime(info.duration)) if info.duration else "Unknown"
        return (
            f"Title: {info.title}\n"
            f"Channel: {info.uploader}\n"
            f"Duration: {duration}\n"
            f"Views: {info.view_count:,}\n"
            f"Likes: {info.like_count:,}\n"
            f"Comments: {info.comment_count:,}\n"
            f"URL: {info.webpage_url}"
        )

    def _format_description(self, info: VideoInfo) -> str:
        description = info.description.strip()
        if description:
            description = "\n".join(description.splitlines()[:8])
        tags = ", ".join(info.tags or [])
        return (
            "Highlights from the video description:\n"
            f"{description if description else 'No description provided.'}\n\n"
            f"Tags: {tags if tags else 'None'}"
        )

    def _fetch_thumbnail(self, url: str | None) -> None:
        if not url:
            return
        try:
            with urlopen(url) as response:
                data = response.read()
            image = Image.open(BytesIO(data)).convert("RGB")
            image.thumbnail((420, 240))
            self.root.after(0, lambda: self._update_thumbnail(image))
        except Exception as exc:
            logging.info("Thumbnail fetch failed: %s", exc)

    def _update_thumbnail(self, image: Image.Image) -> None:
        ctk_image = ctk.CTkImage(light_image=image, dark_image=image, size=image.size)
        self.thumbnail_image = ctk_image
        self.thumbnail_label.configure(image=ctk_image, text="")

    def _download_video(self) -> None:
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Heads up", "Please paste a YouTube link first.")
            return
        self._reset_progress()
        self._set_status("Downloading video...")
        threading.Thread(target=self._download_video_worker, args=(url,), daemon=True).start()

    def _download_audio(self) -> None:
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Heads up", "Please paste a YouTube link first.")
            return
        self._reset_progress()
        self._set_status("Downloading audio...")
        threading.Thread(target=self._download_audio_worker, args=(url,), daemon=True).start()

    def _download_video_worker(self, url: str) -> None:
        ydl_opts = {
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "outtmpl": os.path.join(DOWNLOAD_DIR, "%(title)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": True,
            "progress_hooks": [self._progress_hook],
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            self._set_status("Video downloaded successfully.")
            self.root.after(0, self._refresh_video_list)
        except Exception as exc:
            self._set_status(f"Video download failed: {exc}")

    def _download_audio_worker(self, url: str) -> None:
        ydl_opts = {
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "outtmpl": os.path.join(DOWNLOAD_DIR, "%(title)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": True,
            "progress_hooks": [self._progress_hook],
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            self._set_status("Audio downloaded successfully.")
            self.root.after(0, self._refresh_video_list)
        except Exception as exc:
            self._set_status(f"Audio download failed: {exc}")

    def _refresh_video_list(self) -> None:
        if not os.path.exists(DOWNLOAD_DIR):
            return
        files = sorted(f for f in os.listdir(DOWNLOAD_DIR) if f.lower().endswith(VIDEO_EXTENSIONS))
        self._render_video_list(files)

    def _select_video(self, filename: str) -> None:
        base_path = os.path.join(DOWNLOAD_DIR, os.path.splitext(filename)[0])
        srt_path = f"{base_path}.srt"
        if os.path.exists(srt_path):
            with open(srt_path, "r", encoding="utf-8") as handle:
                self._append_subtitles(handle.read())
            self._set_status("Loaded subtitles from local file.")
        else:
            self._set_status("No saved subtitles for this video yet.")

    def _refresh_languages(self) -> None:
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Heads up", "Please paste a YouTube link first.")
            return
        self._set_status("Fetching available languages...")
        threading.Thread(target=self._refresh_languages_worker, args=(url,), daemon=True).start()

    def _refresh_languages_worker(self, url: str) -> None:
        ydl_opts = {
            "quiet": True,
            "nocheckcertificate": True,
            "skip_download": True,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            self.root.after(0, lambda: self._apply_language_options(info))
            self._set_status("Languages refreshed.")
        except Exception as exc:
            self._set_status(f"Language refresh failed: {exc}")

    def _fetch_comments(self) -> None:
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Heads up", "Please paste a YouTube link first.")
            return
        self._set_status("Fetching top comments...")
        threading.Thread(target=self._fetch_comments_worker, args=(url,), daemon=True).start()

    def _fetch_comments_worker(self, url: str) -> None:
        ydl_opts = {
            "quiet": True,
            "nocheckcertificate": True,
            "skip_download": True,
            "getcomments": True,
            "comment_sort": "top",
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            comments = info.get("comments") or []
            if not comments:
                self.root.after(0, lambda: self._append_comments("No comments available."))
                self._set_status("No comments found.")
                return
            formatted = []
            for idx, comment in enumerate(comments[:10], start=1):
                author = comment.get("author") or "Unknown"
                text = comment.get("text") or ""
                like_count = comment.get("like_count") or 0
                formatted.append(f"{idx}. {author} ({like_count} likes)\n{text}")
            self.root.after(0, lambda: self._append_comments("\n\n".join(formatted)))
            self._set_status("Top comments loaded.")
        except Exception as exc:
            self._set_status(f"Comment fetch failed: {exc}")

    def _extract_links(self) -> None:
        content = self.comments_text.get("1.0", "end")
        links = re.findall(r"https?://\\S+", content)
        self._render_links(links)

    def _apply_language_options(self, info: dict) -> None:
        options, mapping = self._build_language_options(info)
        self.lang_display_map = mapping
        self.lang_combo.configure(values=options)
        if options:
            self.lang_var.set(options[0])

    def _build_language_options(self, info: dict) -> tuple[list[str], dict[str, tuple[str, str]]]:
        manual = info.get("subtitles") or {}
        auto = info.get("automatic_captions") or {}
        options: list[str] = []
        mapping: dict[str, tuple[str, str]] = {}

        def add(lang: str, kind: str) -> None:
            label = f"{lang} ({kind})"
            if label not in mapping:
                options.append(label)
                mapping[label] = (lang, kind)

        for lang in manual.keys():
            add(lang, "Manual")
        for lang in auto.keys():
            add(lang, "Auto")
        for lang in DEFAULT_LANG_PRIORITY:
            add(lang, "Default")

        ordered = self._order_language_labels(options, mapping)
        return ordered, mapping

    def _order_language_labels(
        self, options: list[str], mapping: dict[str, tuple[str, str]]
    ) -> list[str]:
        kind_priority = {"Manual": 0, "Auto": 1, "Default": 2}

        def key(label: str) -> tuple[int, str, int]:
            lang, kind = mapping[label]
            priority = 0 if lang in PREFERRED_LANGS else 1
            return (priority, lang, kind_priority.get(kind, 3))

        return sorted(options, key=key)

    def _download_subtitles(self) -> None:
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Heads up", "Please paste a YouTube link first.")
            return
        self._reset_progress()
        self._set_status("Fetching subtitles from YouTube...")
        threading.Thread(target=self._download_subtitles_worker, args=(url,), daemon=True).start()

    def _download_subtitles_worker(self, url: str) -> None:
        selection = self.lang_combo.get().strip()
        lang, kind = self.lang_display_map.get(
            selection, (selection.split(" ")[0] if selection else DEFAULT_LANG_PRIORITY[0], "Default")
        )
        manual_only = kind == "Manual"
        auto_only = kind == "Auto"
        output_template = os.path.join(DOWNLOAD_DIR, "%(title)s.%(ext)s")
        ydl_opts = {
            "skip_download": True,
            "writesubtitles": manual_only or kind == "Default",
            "writeautomaticsub": auto_only or kind == "Default",
            "subtitleslangs": [lang],
            "subtitlesformat": "srt",
            "outtmpl": output_template,
            "quiet": True,
            "nocheckcertificate": True,
            "progress_hooks": [self._progress_hook],
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                ydl.download([url])
            base_path = os.path.splitext(ydl.prepare_filename(info))[0]
            srt_path = self._resolve_srt_path(base_path, lang)
            if not srt_path:
                self._set_status("No subtitle file found after download.")
                return
            with open(srt_path, "r", encoding="utf-8") as handle:
                subtitle_content = handle.read()
            self.root.after(0, lambda: self._append_subtitles(subtitle_content))
            self.root.after(0, self._copy_subtitles)
            self._set_status("Subtitles fetched and copied.")
            self.root.after(0, self._refresh_video_list)
        except Exception as exc:
            self._set_status(f"Subtitle download failed: {exc}")

    def _resolve_srt_path(self, base_path: str, lang: str) -> str | None:
        patterns = [
            f"{base_path}.{lang}.srt",
            f"{base_path}.srt",
        ]
        for path in patterns:
            if os.path.exists(path):
                return path
        return None

    def _save_srt_as(self) -> None:
        content = self.subtitle_text.get("1.0", "end").strip()
        if not content:
            messagebox.showwarning("Heads up", "No subtitles to save yet.")
            return
        default_name = self.current_title or "subtitle"
        file_path = filedialog.asksaveasfilename(
            initialfile=f"{default_name}.srt",
            defaultextension=".srt",
            filetypes=[("SRT", "*.srt")],
        )
        if not file_path:
            return
        with open(file_path, "w", encoding="utf-8") as handle:
            handle.write(content)
        self._set_status("Subtitle file saved.")

    def _open_in_browser(self) -> None:
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Heads up", "Please paste a YouTube link first.")
            return
        webbrowser.open(url)
        self._set_status("Opened link in your browser.")

    def _open_download_dir(self) -> None:
        path = os.path.abspath(DOWNLOAD_DIR)
        if os.name == "nt":
            os.startfile(path)
        elif os.name == "posix":
            os.system(f"xdg-open '{path}'")
        self._set_status("Download folder opened.")

    def _copy_subtitles(self) -> None:
        content = self.subtitle_text.get("1.0", "end").strip()
        if not content:
            messagebox.showwarning("Heads up", "No subtitles to copy yet.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        self._set_status("Subtitles copied to clipboard.")

    def _reset_progress(self) -> None:
        self.progress_bar.set(0)
        self.speed_var.set("Speed: —")
        self.eta_var.set("ETA: —")
        self.size_var.set("Size: —")

    def _progress_hook(self, status: dict) -> None:
        if status.get("status") != "downloading":
            if status.get("status") == "finished":
                self.progress_bar.set(1)
            return
        downloaded = status.get("downloaded_bytes") or 0
        total = status.get("total_bytes") or status.get("total_bytes_estimate") or 0
        speed = status.get("speed") or 0
        eta = status.get("eta") or 0
        progress = (downloaded / total) if total else 0
        size_text = f"Size: {self._format_bytes(total) if total else '—'}"
        speed_text = f"Speed: {self._format_bytes(speed)}/s" if speed else "Speed: —"
        eta_text = f"ETA: {int(eta)}s" if eta else "ETA: —"

        def update() -> None:
            self.progress_bar.set(progress)
            self.size_var.set(size_text)
            self.speed_var.set(speed_text)
            self.eta_var.set(eta_text)

        self.root.after(0, update)

    @staticmethod
    def _format_bytes(amount: float) -> str:
        if amount <= 0:
            return "0 B"
        units = ["B", "KB", "MB", "GB", "TB"]
        index = 0
        while amount >= 1024 and index < len(units) - 1:
            amount /= 1024
            index += 1
        return f"{amount:.1f} {units[index]}"

    def _poll_queue(self) -> None:
        try:
            while True:
                self.queue.get_nowait()
        except Empty:
            pass
        self.root.after(250, self._poll_queue)


def main() -> None:
    root = ctk.CTk()
    app = EagleV75App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
