import sys, asyncio, json, os, threading, random, hashlib
from datetime import datetime

try:
    import customtkinter as ctk
    import tkinter as tk
    from telethon import TelegramClient, utils
    from telethon.tl.types import DocumentAttributeFilename
    import pygame
except Exception as e:
    print("Ошибка: pip install customtkinter telethon pygame")
    sys.exit(1)

try:
    from mutagen.id3 import ID3, APIC
    HAS_MUTAGEN = True
except ImportError:
    HAS_MUTAGEN = False

# ====================== CONFIG ======================
API_ID   = 2040
API_HASH = "b18441a1ff607e10a989891a5462e627"
PHONE    = "+79038813059"

BASE_DIR = os.path.expanduser("~/MP3_Tracker_Data")
os.makedirs(BASE_DIR, exist_ok=True)

DATA_FILE          = os.path.join(BASE_DIR, "tracked_mp3s.json")
CHATS_FILE         = os.path.join(BASE_DIR, "my_chats_v3.json")
LOCAL_FOLDERS_FILE = os.path.join(BASE_DIR, "local_folders.json")
PACKS_FILE         = os.path.join(BASE_DIR, "beat_packs.json")
SENT_PACKS_FILE    = os.path.join(BASE_DIR, "sent_packs.json")
SESSION_NAME       = os.path.join(BASE_DIR, "session")

# ====================== PALETTE ======================
CLR_BG       = "#07080F"
CLR_PANEL    = "#0D0E1C"
CLR_CARD     = "#13142A"
CLR_CARD_HOV = "#1A1B36"
CLR_ACCENT   = "#7C2EFF"
CLR_ACCENT2  = "#9B5FFF"
CLR_CYAN     = "#00D0FF"
CLR_MAGENTA  = "#FF2D78"
CLR_GREEN    = "#00E676"
CLR_YELLOW   = "#FFD740"
CLR_TEXT     = "#E8E9F2"
CLR_MUTED    = "#4E5070"
CLR_BORDER   = "#1E1F3A"
CLR_SUCCESS  = "#00C853"
CLR_WARN     = "#FF6D00"

PACK_COLORS = [
    "#7C2EFF","#FF2D78","#00D0FF","#00E676","#FFD740",
    "#FF6D00","#E040FB","#00BCD4","#FF5722","#69F0AE",
    "#F06292","#4FC3F7","#AED581","#FFD54F","#CE93D8",
]

ctk.set_appearance_mode("dark")

BAR_COUNT = 22
ANIM_MS   = 70
SUPPORTED = ('.mp3', '.wav', '.m4a', '.flac', '.ogg', '.aac')

# ─────────────────────────────────────────────────────
class MP3TrackerApp(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title("elentflow MP3 Tracker v7")
        self.geometry("1720x990")
        self.minsize(1280, 760)
        self.configure(fg_color=CLR_BG)

        self.client       = TelegramClient(SESSION_NAME, API_ID, API_HASH)
        self.is_connected = False
        self.current_chat = None

        self.chats              = self.load_chats()
        self.tracked_files      = self.load_tracked()
        self.local_folders      = self.load_local_folders()
        self.packs              = self.load_packs()
        self.sent_packs         = self.load_sent_packs()
        self.missing_files_data = []
        self.missing_check_vars = {}
        self.playing_buttons    = {}
        self.active_folder      = None
        self._view_mode         = "files"

        self.current_playing  = None
        self.current_path_idx = -1
        self.is_paused        = False
        self.is_seeking       = False
        self.seek_start_time  = 0.0
        self.current_duration = 0.0
        self.volume           = 0.7
        self.shuffle_mode     = False
        self._was_busy        = False
        pygame.mixer.init()
        pygame.mixer.music.set_volume(self.volume)

        self._bar_cur  = [4.0] * BAR_COUNT
        self._bar_tgt  = [4.0] * BAR_COUNT
        self._bar_tick = 0

        self._is_scanning        = False
        self._last_playing_name  = None
        self._count_update_job   = None
        self._vis_bars_ids       = []
        self._vis_w_cached       = 0
        self._vis_h_cached       = 0

        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self._run_loop, daemon=True).start()

        self.create_layout()
        self._animate()
        asyncio.run_coroutine_threadsafe(self.connect_tg(), self.loop)

    # ─── helpers ───
    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def _fmt_size(self, b):
        if not b: return ""
        if b < 1024:    return f"{b} B"
        if b < 1048576: return f"{b/1024:.1f} KB"
        return f"{b/1048576:.1f} MB"

    def _fmt_time(self, s):
        s = max(0, int(s))
        return f"{s//60}:{s%60:02d}"

    # ─── load/save ───
    def _jload(self, path):
        if os.path.exists(path):
            try:
                with open(path, encoding='utf-8') as f: return json.load(f)
            except: pass
        return {}

    def _jsave(self, path, data):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_tracked(self):       return self._jload(DATA_FILE)
    def save_tracked(self):       self._jsave(DATA_FILE, self.tracked_files)
    def load_chats(self):         return self._jload(CHATS_FILE)
    def save_chats(self):         self._jsave(CHATS_FILE, self.chats)
    def load_packs(self):         return self._jload(PACKS_FILE)
    def save_packs(self):         self._jsave(PACKS_FILE, self.packs)
    def load_sent_packs(self):    return self._jload(SENT_PACKS_FILE)
    def save_sent_packs(self):    self._jsave(SENT_PACKS_FILE, self.sent_packs)

    def load_local_folders(self):
        data = self._jload(LOCAL_FOLDERS_FILE)
        for k, v in data.items():
            if isinstance(v, str): data[k] = [v]
        return data

    def save_local_folders(self):
        self._jsave(LOCAL_FOLDERS_FILE, self.local_folders)

    # ─── pack ops ───
    def _gen_pack_id(self):
        import time
        return f"pack_{int(time.time()*1000) % 9999999999}"

    def create_pack(self, name, files=None, color=None):
        pid   = self._gen_pack_id()
        color = color or PACK_COLORS[len(self.packs) % len(PACK_COLORS)]
        self.packs[pid] = {
            "name":    name,
            "files":   list(files) if files else [],
            "color":   color,
            "created": datetime.now().strftime("%d.%m.%Y")
        }
        self.save_packs()
        return pid

    def delete_pack(self, pack_id):
        self.packs.pop(pack_id, None)
        for chat in self.sent_packs.values():
            chat.pop(pack_id, None)
        self.save_packs()
        self.save_sent_packs()

    def mark_pack_sent(self, pid, chat_raw):
        self.sent_packs.setdefault(chat_raw, {})[pid] = datetime.now().strftime("%d.%m.%Y")
        self.save_sent_packs()

    def unmark_pack_sent(self, pid, chat_raw):
        if chat_raw in self.sent_packs:
            self.sent_packs[chat_raw].pop(pid, None)
        self.save_sent_packs()

    def is_pack_sent(self, pid, chat_raw):
        return bool(self.sent_packs.get(chat_raw, {}).get(pid))

    def _get_cover_hash(self, path):
        if not HAS_MUTAGEN: return None
        try:
            tags = ID3(path)
            for tag in tags.values():
                if isinstance(tag, APIC):
                    return hashlib.md5(tag.data).hexdigest()
        except Exception: pass
        return None

    def auto_detect_packs_by_cover(self, progress_cb=None):
        all_folders = set()
        for folders in self.local_folders.values():
            all_folders.update(folders)
        total_files = []
        for folder in all_folders:
            if not os.path.exists(folder): continue
            for fname in sorted(os.listdir(folder)):
                if fname.lower().endswith(SUPPORTED):
                    total_files.append(os.path.join(folder, fname))
        groups   = {}
        no_cover = []
        for i, path in enumerate(total_files):
            if progress_cb: progress_cb(i, len(total_files))
            h = self._get_cover_hash(path)
            if h: groups.setdefault(h, []).append(path)
            else: no_cover.append(path)
        return groups, no_cover


    # ─────────────────────────────────────────────────────
    #  LAYOUT
    # ─────────────────────────────────────────────────────
    def create_layout(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # ═══ LEFT SIDEBAR ═══
        self.sidebar = ctk.CTkFrame(self, width=295, fg_color=CLR_PANEL, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.pack_propagate(False)

        sb_hdr = ctk.CTkFrame(self.sidebar, fg_color=CLR_CARD, corner_radius=0, height=64)
        sb_hdr.pack(fill="x"); sb_hdr.pack_propagate(False)

        ctk.CTkLabel(sb_hdr, text="ARTISTS",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=CLR_CYAN).pack(side="left", padx=18, pady=18)

        dot_frame = ctk.CTkFrame(sb_hdr, fg_color="transparent")
        dot_frame.pack(side="right", padx=10)
        self.dot_canvas = tk.Canvas(dot_frame, width=10, height=10,
                                    bg=CLR_CARD, highlightthickness=0)
        self.dot_canvas.pack()
        self._tg_dot = self.dot_canvas.create_oval(1,1,9,9, fill=CLR_MUTED, outline="")
        ctk.CTkLabel(dot_frame, text="TG", font=ctk.CTkFont(size=9),
                     text_color=CLR_MUTED).pack()

        self.btn_tg_connect = ctk.CTkButton(
            sb_hdr, text="ВОЙТИ", width=58, height=30, corner_radius=8,
            fg_color=CLR_CARD, hover_color=CLR_CARD_HOV,
            text_color=CLR_CYAN, font=ctk.CTkFont(size=11, weight="bold"),
            command=self.open_tg_auth)
        self.btn_tg_connect.pack(side="right", padx=4)

        self.chat_list_scroll = ctk.CTkScrollableFrame(
            self.sidebar, fg_color="transparent", scrollbar_button_color=CLR_BORDER)
        self.chat_list_scroll.pack(fill="both", expand=True, padx=8, pady=6)

        add_f = ctk.CTkFrame(self.sidebar, fg_color=CLR_CARD, height=52, corner_radius=12)
        add_f.pack(fill="x", padx=12, pady=14); add_f.pack_propagate(False)
        self.chat_entry = ctk.CTkEntry(add_f, placeholder_text="@username or link…",
                                       fg_color="transparent", border_width=0,
                                       font=ctk.CTkFont(size=13), text_color=CLR_TEXT)
        self.chat_entry.pack(side="left", fill="both", expand=True, padx=10)
        self.chat_entry.bind("<Return>", lambda e: self.add_chat())
        ctk.CTkButton(add_f, text="+", width=40, height=40, corner_radius=10,
                      fg_color=CLR_ACCENT, hover_color=CLR_ACCENT2,
                      font=ctk.CTkFont(size=20, weight="bold"),
                      command=self.add_chat).pack(side="right", padx=6)

        # ═══ MAIN WORKSPACE ═══
        self.main_work = ctk.CTkFrame(self, fg_color=CLR_BG)
        self.main_work.grid(row=0, column=1, sticky="nsew", padx=20)
        self.main_work.grid_columnconfigure(0, weight=1)
        self.main_work.grid_rowconfigure(2, weight=1)

        # Top bar
        top_bar = ctk.CTkFrame(self.main_work, fg_color="transparent")
        top_bar.grid(row=0, column=0, sticky="ew", pady=(16,4))

        title_f = ctk.CTkFrame(top_bar, fg_color="transparent")
        title_f.pack(side="left")
        ctk.CTkLabel(title_f, text="elentflow",
                     font=ctk.CTkFont(size=30, weight="bold"),
                     text_color=CLR_CYAN).pack(side="left")
        ctk.CTkLabel(title_f, text="  MP3 TRACKER",
                     font=ctk.CTkFont(size=30, weight="bold"),
                     text_color=CLR_TEXT).pack(side="left")

        self.lbl_status = ctk.CTkLabel(top_bar, text="",
                                        font=ctk.CTkFont(size=11), text_color=CLR_MUTED)
        self.lbl_status.pack(side="left", padx=20)

        _b = dict(height=42, width=44, fg_color=CLR_CARD, corner_radius=10)
        ctk.CTkButton(top_bar, text="📊", font=("Segoe UI Emoji",17),
                      hover_color=CLR_CARD_HOV,
                      command=self.open_pack_dashboard, **_b).pack(side="right", padx=3)
        ctk.CTkButton(top_bar, text="📦", font=("Segoe UI Emoji",17),
                      hover_color=CLR_CARD_HOV,
                      command=self.open_pack_manager, **_b).pack(side="right", padx=3)
        ctk.CTkButton(top_bar, text="🔍", font=("Segoe UI Emoji",17),
                      hover_color=CLR_CARD_HOV,
                      command=self.open_chat_analyzer, **_b).pack(side="right", padx=3)
        ctk.CTkButton(top_bar, text="📋", font=("Segoe UI Emoji",17),
                      hover_color=CLR_CARD_HOV,
                      command=self.open_bulk_import, **_b).pack(side="right", padx=3)
        ctk.CTkButton(top_bar, text="📁", font=("Segoe UI Emoji",17),
                      hover_color=CLR_CARD_HOV,
                      command=self.open_folder_manager, **_b).pack(side="right", padx=3)
        self.btn_scan = ctk.CTkButton(top_bar, text="🔄", font=("Segoe UI Emoji",17),
                                      hover_color=CLR_CARD_HOV,
                                      command=self.scan_current, **_b)
        self.btn_scan.pack(side="right", padx=3)

        # Mid bar
        mid_bar = ctk.CTkFrame(self.main_work, fg_color="transparent")
        mid_bar.grid(row=1, column=0, sticky="ew", pady=10)
        mid_bar.columnconfigure(0, weight=1)

        self.search_entry = ctk.CTkEntry(
            mid_bar, placeholder_text="🔍  Search tracks…",
            fg_color=CLR_PANEL, border_color=CLR_BORDER,
            height=46, corner_radius=12, font=ctk.CTkFont(size=13), text_color=CLR_TEXT)
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0,12))
        self.search_entry.bind("<KeyRelease>",
            lambda e: self.select_chat(self.current_chat, force_reload=True))

        self.btn_send = ctk.CTkButton(
            mid_bar, text="🚀  SEND", height=46, width=155,
            fg_color=CLR_MAGENTA, hover_color="#CC1F5F",
            font=ctk.CTkFont(size=13, weight="bold"),
            corner_radius=12, command=self.send_files)
        self.btn_send.grid(row=0, column=1, sticky="e")

        # Lists
        self.lists_frame = ctk.CTkFrame(self.main_work, fg_color="transparent")
        self.lists_frame.grid(row=2, column=0, sticky="nsew")
        self.lists_frame.grid_columnconfigure(0, weight=1)
        self.lists_frame.grid_columnconfigure(1, weight=1)
        self.lists_frame.grid_rowconfigure(0, weight=1)

        # History column
        c_sent = ctk.CTkFrame(self.lists_frame, fg_color="transparent")
        c_sent.grid(row=0, column=0, sticky="nsew", padx=(0,10))
        hist_hdr = ctk.CTkFrame(c_sent, fg_color="transparent")
        hist_hdr.pack(fill="x", pady=(0,6))
        ctk.CTkLabel(hist_hdr, text="▸ HISTORY",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=CLR_CYAN).pack(side="left")
        self.lbl_sent_count = ctk.CTkLabel(hist_hdr, text="",
                                            font=ctk.CTkFont(size=11), text_color=CLR_MUTED)
        self.lbl_sent_count.pack(side="left", padx=8)
        self.scroll_sent = ctk.CTkScrollableFrame(
            c_sent, fg_color=CLR_PANEL, corner_radius=14,
            scrollbar_button_color=CLR_BORDER)
        self.scroll_sent.pack(fill="both", expand=True)

        # Beats / Packs column
        c_local = ctk.CTkFrame(self.lists_frame, fg_color="transparent")
        c_local.grid(row=0, column=1, sticky="nsew", padx=(10,0))
        local_hdr = ctk.CTkFrame(c_local, fg_color="transparent")
        local_hdr.pack(fill="x", pady=(0,4))

        # View mode toggle buttons
        self._vm_files_btn = ctk.CTkButton(
            local_hdr, text="▸ BEATS", height=28, width=84,
            fg_color=CLR_ACCENT, hover_color=CLR_ACCENT2,
            text_color=CLR_TEXT, corner_radius=7,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=lambda: self._set_view_mode("files"))
        self._vm_files_btn.pack(side="left")

        self._vm_packs_btn = ctk.CTkButton(
            local_hdr, text="📦 PACKS", height=28, width=100,
            fg_color=CLR_CARD, hover_color=CLR_CARD_HOV,
            text_color=CLR_MUTED, corner_radius=7,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=lambda: self._set_view_mode("packs"))
        self._vm_packs_btn.pack(side="left", padx=4)

        self.lbl_selected_count = ctk.CTkLabel(
            local_hdr, text="", font=ctk.CTkFont(size=11),
            text_color=CLR_MUTED, width=200, anchor="w")
        self.lbl_selected_count.pack(side="left", padx=8)

        sel_f = ctk.CTkFrame(local_hdr, fg_color="transparent")
        sel_f.pack(side="right")
        _sb = dict(height=26, corner_radius=6, fg_color=CLR_CARD,
                   hover_color=CLR_CARD_HOV, font=ctk.CTkFont(size=11, weight="bold"))
        ctk.CTkButton(sel_f, text="ALL",  width=46, text_color=CLR_GREEN,
                      command=self._select_all,  **_sb).pack(side="left", padx=2)
        ctk.CTkButton(sel_f, text="NONE", width=50, text_color=CLR_MUTED,
                      command=self._select_none, **_sb).pack(side="left", padx=2)

        self.folder_tabs_frame = ctk.CTkScrollableFrame(
            c_local, orientation="horizontal", fg_color="transparent", height=36)
        self.folder_tabs_frame.pack(fill="x", pady=(0,5))

        self.scroll_local = ctk.CTkScrollableFrame(
            c_local, fg_color=CLR_PANEL, corner_radius=14,
            scrollbar_button_color=CLR_BORDER)
        self.scroll_local.pack(fill="both", expand=True)

        self.bind("<Map>", self._on_window_restore)
        self._build_player()

    def _build_player(self):
        self.player_panel = ctk.CTkFrame(
            self.main_work, height=120, fg_color=CLR_PANEL, corner_radius=18)
        self.player_panel.grid(row=3, column=0, sticky="ew", pady=(14,18))
        self.player_panel.pack_propagate(False)

        p = ctk.CTkFrame(self.player_panel, fg_color="transparent")
        p.pack(fill="both", expand=True, padx=20, pady=10)

        p_top = ctk.CTkFrame(p, fg_color="transparent")
        p_top.pack(fill="x")
        self.lbl_now_playing = ctk.CTkLabel(
            p_top, text="●  READY TO PLAY",
            font=ctk.CTkFont(size=13, weight="bold"), text_color=CLR_MUTED)
        self.lbl_now_playing.pack(side="left")
        self.lbl_time = ctk.CTkLabel(
            p_top, text="0:00 / 0:00",
            font=ctk.CTkFont("Courier", size=12), text_color=CLR_MUTED)
        self.lbl_time.pack(side="right")

        p_bot = ctk.CTkFrame(p, fg_color="transparent")
        p_bot.pack(fill="x", pady=(8,0))

        self.vis_canvas = tk.Canvas(p_bot, bg=CLR_PANEL,
                                    highlightthickness=0, width=140, height=40)
        self.vis_canvas.pack(side="left", padx=(0,12))

        ctrl = ctk.CTkFrame(p_bot, fg_color="transparent")
        ctrl.pack(side="left")
        _cb = dict(width=36, height=36, corner_radius=8,
                   fg_color=CLR_CARD, hover_color=CLR_CARD_HOV,
                   font=ctk.CTkFont(size=14, weight="bold"))
        self.btn_shuffle = ctk.CTkButton(ctrl, text="⇄", text_color=CLR_MUTED,
                                          command=self.toggle_shuffle, **_cb)
        self.btn_shuffle.pack(side="left", padx=3)
        ctk.CTkButton(ctrl, text="⏮", text_color=CLR_TEXT,
                      command=self.play_prev, **_cb).pack(side="left", padx=3)
        self.btn_play_main = ctk.CTkButton(
            ctrl, text="▶", width=44, height=44, corner_radius=12,
            fg_color=CLR_ACCENT, hover_color=CLR_ACCENT2, text_color=CLR_TEXT,
            font=ctk.CTkFont(size=16, weight="bold"),
            command=lambda: self.toggle_pause() if self.current_playing else None)
        self.btn_play_main.pack(side="left", padx=3)
        ctk.CTkButton(ctrl, text="⏭", text_color=CLR_TEXT,
                      command=self.play_next, **_cb).pack(side="left", padx=3)
        ctk.CTkButton(ctrl, text="⏹", text_color=CLR_MAGENTA,
                      command=self.stop_audio, **_cb).pack(side="left", padx=3)

        prog_f = ctk.CTkFrame(p_bot, fg_color="transparent")
        prog_f.pack(side="left", fill="x", expand=True, padx=16)
        self.slider_progress = ctk.CTkSlider(
            prog_f, from_=0, to=100,
            fg_color=CLR_CARD, progress_color=CLR_ACCENT,
            button_color=CLR_ACCENT2, button_hover_color=CLR_ACCENT, height=16)
        self.slider_progress.pack(fill="x")
        self.slider_progress.set(0)
        self.slider_progress.bind("<ButtonPress-1>",   self._seek_start)
        self.slider_progress.bind("<ButtonRelease-1>", self._seek_end)

        vol_f = ctk.CTkFrame(p_bot, fg_color="transparent")
        vol_f.pack(side="right", padx=(16,0))
        self.lbl_vol_icon = ctk.CTkLabel(vol_f, text="🔊",
                                          font=ctk.CTkFont(size=14), text_color=CLR_MUTED)
        self.lbl_vol_icon.pack(side="left", padx=(0,4))
        self.slider_vol = ctk.CTkSlider(
            vol_f, from_=0, to=1, width=90,
            fg_color=CLR_CARD, progress_color=CLR_ACCENT2,
            button_color=CLR_MUTED, button_hover_color=CLR_TEXT,
            height=14, command=self.set_volume)
        self.slider_vol.pack(side="left")
        self.slider_vol.set(self.volume)


    # ─── view mode ───
    def _set_view_mode(self, mode):
        self._view_mode = mode
        if mode == "files":
            self._vm_files_btn.configure(fg_color=CLR_ACCENT, text_color=CLR_TEXT)
            self._vm_packs_btn.configure(fg_color=CLR_CARD,   text_color=CLR_MUTED)
        else:
            self._vm_files_btn.configure(fg_color=CLR_CARD,   text_color=CLR_MUTED)
            self._vm_packs_btn.configure(fg_color=CLR_ACCENT,  text_color=CLR_TEXT)
        if self.current_chat:
            self.select_chat(self.current_chat, force_reload=True)

    # ─── seek ───
    def _seek_start(self, e): self.is_seeking = True

    def _seek_end(self, e):
        self.is_seeking = False
        pos = self.slider_progress.get()
        if self.current_playing and self.current_duration > 0:
            self.seek_start_time = pos
            try:
                pygame.mixer.music.play(start=pos)
                self.is_paused = False
                self.btn_play_main.configure(text="⏸")
                self.update_ui_buttons()
            except Exception: pass

    # ─── folder manager ───
    def open_folder_manager(self):
        if not self.current_chat:
            self.set_status("Сначала выбери артиста", CLR_WARN); return
        win = ctk.CTkToplevel(self)
        win.title(f"Папки — {self.chats[self.current_chat]['display']}")
        win.geometry("480x400"); win.configure(fg_color=CLR_BG)
        win.grab_set(); win.lift()
        ctk.CTkLabel(win, text="📁  ЛОКАЛЬНЫЕ ПАПКИ",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=CLR_CYAN).pack(pady=(18,8))
        scroll = ctk.CTkScrollableFrame(win, fg_color=CLR_PANEL, corner_radius=12)
        scroll.pack(fill="both", expand=True, padx=18, pady=(0,8))

        def refresh_list():
            for w in scroll.winfo_children(): w.destroy()
            folders = self.local_folders.get(self.current_chat, [])
            if not folders:
                ctk.CTkLabel(scroll, text="Нет папок", text_color=CLR_MUTED).pack(pady=20)
            for fp in folders:
                row = ctk.CTkFrame(scroll, fg_color=CLR_CARD, corner_radius=8)
                row.pack(fill="x", pady=3, padx=4)
                ctk.CTkLabel(row, text=fp, font=ctk.CTkFont(size=11),
                             text_color=CLR_TEXT, anchor="w").pack(
                    side="left", padx=10, pady=8, fill="x", expand=True)
                def _rm(f=fp):
                    lst = self.local_folders.get(self.current_chat, [])
                    if f in lst: lst.remove(f)
                    self.local_folders[self.current_chat] = lst
                    self.save_local_folders(); refresh_list()
                    self._update_folder_tabs()
                    self.select_chat(self.current_chat, force_reload=True)
                ctk.CTkButton(row, text="×", width=28, height=28,
                              fg_color="transparent", text_color=CLR_MAGENTA,
                              hover_color=CLR_CARD_HOV, command=_rm).pack(side="right", padx=6)

        def add_folder():
            from tkinter import filedialog
            folder = filedialog.askdirectory(parent=win)
            if not folder: return
            lst = self.local_folders.setdefault(self.current_chat, [])
            if folder not in lst: lst.append(folder)
            self.save_local_folders(); refresh_list()
            self.after(0, lambda: (
                self._update_folder_tabs(),
                self.select_chat(self.current_chat, force_reload=True)))

        refresh_list()
        btn_f = ctk.CTkFrame(win, fg_color="transparent")
        btn_f.pack(fill="x", padx=18, pady=12)
        ctk.CTkButton(btn_f, text="➕  Добавить папку", height=42,
                      fg_color=CLR_ACCENT, hover_color=CLR_ACCENT2,
                      font=ctk.CTkFont(weight="bold"),
                      corner_radius=10, command=add_folder).pack(side="left")

    # ─── folder tabs ───
    def _update_folder_tabs(self):
        for w in self.folder_tabs_frame.winfo_children(): w.destroy()
        folders = self.local_folders.get(self.current_chat, [])
        if not folders: return
        def make_tab(label, fv):
            active = (self.active_folder == fv)
            ctk.CTkButton(
                self.folder_tabs_frame, text=label, height=26,
                fg_color=CLR_ACCENT if active else CLR_CARD, text_color=CLR_TEXT,
                hover_color=CLR_ACCENT if not active else "#5A20CC",
                corner_radius=7, font=ctk.CTkFont(size=11, weight="bold"),
                command=lambda f=fv: self._set_active_folder(f)
            ).pack(side="left", padx=3)
        make_tab("Все", None)
        for f in folders:
            make_tab(os.path.basename(f), f)

    def _set_active_folder(self, fv):
        self.active_folder = fv
        self._update_folder_tabs()
        if self.current_chat:
            self.select_chat(self.current_chat, force_reload=True)

    # ─── selected count ───
    def _schedule_count_update(self):
        if self._count_update_job: self.after_cancel(self._count_update_job)
        self._count_update_job = self.after(80, self._update_selected_count)

    def _update_selected_count(self):
        total     = len(self.missing_check_vars)
        size_map  = {m['name']: m.get('size', 0) for m in self.missing_files_data}
        sel_names = [n for n, v in self.missing_check_vars.items() if v.get()]
        selected  = len(sel_names)
        total_b   = sum(size_map.get(n, 0) for n in sel_names)
        if total > 0:
            w_str = f"  ·  {self._fmt_size(total_b)}" if selected else ""
            self.lbl_selected_count.configure(
                text=f"✔ {selected}/{total}{w_str}",
                text_color=CLR_CYAN if selected else CLR_MUTED)
        else:
            self.lbl_selected_count.configure(text="")

    def _select_all(self):
        for v in self.missing_check_vars.values(): v.set(True)
        self._update_selected_count()

    def _select_none(self):
        for v in self.missing_check_vars.values(): v.set(False)
        self._update_selected_count()


    # ─────────────────────────────────────────────────────
    #  RENDER FILES
    # ─────────────────────────────────────────────────────
    def _render_files(self, sent, missing):
        self.playing_buttons    = {}
        self.missing_check_vars = {}
        self.missing_files_data = missing

        for w in self.scroll_sent.winfo_children():  w.destroy()
        for w in self.scroll_local.winfo_children(): w.destroy()

        font_main = ctk.CTkFont(size=13, weight="bold")
        font_sub  = ctk.CTkFont(size=11)

        cnt = len(sent)
        self.lbl_sent_count.configure(text=f"({cnt})" if cnt else "", text_color=CLR_MUTED)

        if not sent:
            ctk.CTkLabel(self.scroll_sent,
                         text="Нет истории\nОтсканируй чат для загрузки треков",
                         text_color=CLR_MUTED, font=ctk.CTkFont(size=12),
                         justify="center").pack(expand=True, pady=50)

        # ── History (batched render) ──
        BATCH = 50
        def _render_sent_chunk(items, start):
            end = min(start + BATCH, len(items))
            for f in items[start:end]:
                row = ctk.CTkFrame(self.scroll_sent, fg_color=CLR_CARD, corner_radius=10)
                row.pack(fill="x", pady=3, padx=4)
                inner = ctk.CTkFrame(row, fg_color="transparent")
                inner.pack(side="left", fill="x", expand=True, padx=12, pady=10)
                name    = f['name']
                display = name if len(name) < 60 else name[:57] + "…"
                ctk.CTkLabel(inner, text=display, font=font_main, anchor="w").pack(anchor="w")
                sz   = self._fmt_size(f.get('size'))
                info = f"{sz}  {f['date']}" if sz else f['date']
                ctk.CTkLabel(row, text=info, text_color=CLR_CYAN, font=font_sub).pack(
                    side="right", padx=12)
            if end < len(items):
                self.after(0, lambda: _render_sent_chunk(items, end))
        _render_sent_chunk(sent, 0)

        # ── Right column ──
        if self._view_mode == "packs":
            self._render_pack_cards()
        else:
            self._render_beats_list(missing, font_main, font_sub)

    def _render_beats_list(self, missing, font_main, font_sub):
        if not missing:
            ctk.CTkLabel(self.scroll_local,
                         text="🎉  Все биты отправлены!\nили нет добавленных папок",
                         text_color=CLR_MUTED, font=ctk.CTkFont(size=12),
                         justify="center").pack(expand=True, pady=50)
            return

        BATCH = 50
        def _render_chunk(items, start):
            end = min(start + BATCH, len(items))
            for idx in range(start, end):
                m          = items[idx]
                is_playing = (self.current_playing == m['path'])
                row = ctk.CTkFrame(self.scroll_local, fg_color=CLR_CARD, corner_radius=10)
                row.pack(fill="x", pady=3, padx=4)
                row.columnconfigure(0, minsize=42, weight=0)
                row.columnconfigure(1, minsize=46, weight=0)
                row.columnconfigure(2, weight=1)
                row.columnconfigure(3, minsize=120, weight=0)

                var = ctk.BooleanVar()
                var.trace_add("write", lambda *_: self._schedule_count_update())
                self.missing_check_vars[m['name']] = var

                ctk.CTkCheckBox(row, text="", variable=var, width=24,
                                fg_color=CLR_ACCENT, checkmark_color="white",
                                hover_color=CLR_ACCENT2).grid(
                    row=0, column=0, padx=(10,0), pady=10, sticky="w")

                p_clr = CLR_CYAN if is_playing else CLR_PANEL
                t_clr = "black"  if is_playing else CLR_CYAN
                txt   = "⏸" if (is_playing and not self.is_paused) else "▶"
                p_btn = ctk.CTkButton(
                    row, text=txt, width=34, height=34, corner_radius=8,
                    fg_color=p_clr, text_color=t_clr,
                    font=ctk.CTkFont(size=12, weight="bold"),
                    command=lambda i=idx, path=m['path']: self._play_by_idx(i, path))
                p_btn.grid(row=0, column=1, padx=4, pady=10)
                self.playing_buttons[m['name']] = p_btn

                name    = m['name']
                display = name if len(name) < 55 else name[:52] + "…"
                ctk.CTkLabel(row, text=display, font=font_main, anchor="w").grid(
                    row=0, column=2, padx=8, pady=10, sticky="ew")

                rf = ctk.CTkFrame(row, fg_color="transparent")
                rf.grid(row=0, column=3, padx=10, pady=10, sticky="e")
                if self.active_folder is None and m.get('folder'):
                    ctk.CTkLabel(rf, text=f"📂 {os.path.basename(m['folder'])}",
                                 text_color=CLR_MUTED, font=font_sub).pack(anchor="e")
                sz = self._fmt_size(m.get('size'))
                if sz:
                    ctk.CTkLabel(rf, text=sz, text_color=CLR_MUTED, font=font_sub).pack(anchor="e")

            if end < len(items):
                self.after(0, lambda: _render_chunk(items, end))
            else:
                self._update_selected_count()

        _render_chunk(missing, 0)

    # ─────────────────────────────────────────────────────
    #  PACK CARDS  (artist view — right column)
    # ─────────────────────────────────────────────────────
    def _render_pack_cards(self):
        for w in self.scroll_local.winfo_children(): w.destroy()

        if not self.packs:
            ctk.CTkLabel(
                self.scroll_local,
                text="📦  Нет паков\n\nОткрой менеджер (📦) чтобы создать пак\nили авто-определить по обложке",
                text_color=CLR_MUTED, font=ctk.CTkFont(size=12),
                justify="center").pack(expand=True, pady=50)
            return

        chat_raw   = self.current_chat
        real_id    = self.chats[chat_raw].get("real_id", chat_raw) if chat_raw else None
        sent_names = set()
        if real_id and real_id in self.tracked_files:
            sent_names = {f['name'] for f in self.tracked_files[real_id]}

        font_title = ctk.CTkFont(size=13, weight="bold")
        font_sub   = ctk.CTkFont(size=11)

        not_sent_count = sum(1 for pid in self.packs if not self.is_pack_sent(pid, chat_raw))
        self.lbl_selected_count.configure(
            text=f"📦 {not_sent_count} не отправлено" if not_sent_count else "✅ Все паки отправлены",
            text_color=CLR_WARN if not_sent_count else CLR_GREEN)

        for pack_id, pack in self.packs.items():
            is_sent    = self.is_pack_sent(pack_id, chat_raw)
            sent_date  = self.sent_packs.get(chat_raw, {}).get(pack_id, "")
            color      = pack.get("color", CLR_ACCENT)
            pack_files = pack.get("files", [])
            overlap    = sum(1 for f in pack_files if f in sent_names)

            card_bg = "#0B1A0B" if is_sent else CLR_CARD
            card = ctk.CTkFrame(self.scroll_local, fg_color=card_bg, corner_radius=12)
            card.pack(fill="x", pady=5, padx=4)

            # Color strip
            strip_c = tk.Canvas(card, width=6, highlightthickness=0, bg=color)
            strip_c.pack(side="left", fill="y")

            content = ctk.CTkFrame(card, fg_color="transparent")
            content.pack(side="left", fill="both", expand=True, padx=12, pady=10)

            trow = ctk.CTkFrame(content, fg_color="transparent")
            trow.pack(fill="x")
            ctk.CTkLabel(trow, text=f"📦  {pack['name']}",
                         font=font_title, text_color=CLR_TEXT).pack(side="left")
            ctk.CTkLabel(trow, text=f"  ·  {len(pack_files)} бит",
                         font=font_sub, text_color=CLR_MUTED).pack(side="left")

            if is_sent:
                ctk.CTkLabel(trow, text=f"  ✓ Отправлен {sent_date}",
                             font=font_sub, text_color=CLR_GREEN).pack(side="left", padx=8)
            elif overlap > 0:
                ctk.CTkLabel(trow,
                             text=f"  ⚠ {overlap} файл(ов) уже в истории чата",
                             font=font_sub, text_color=CLR_YELLOW).pack(side="left", padx=8)

            if pack_files:
                names   = [os.path.splitext(f)[0] for f in pack_files[:5]]
                preview = ",  ".join(names)
                if len(pack_files) > 5: preview += f"  +{len(pack_files)-5}"
                ctk.CTkLabel(content, text=preview, font=font_sub,
                             text_color=CLR_MUTED, anchor="w",
                             wraplength=500).pack(anchor="w", pady=(3,0))

            if chat_raw:
                if is_sent:
                    ctk.CTkButton(
                        card, text="↩ Снять", width=90, height=28,
                        fg_color="transparent", text_color=CLR_MUTED,
                        hover_color=CLR_CARD_HOV, corner_radius=8, font=font_sub,
                        command=lambda pid=pack_id: self._toggle_pack_sent(pid)
                    ).pack(side="right", padx=12, pady=10)
                else:
                    ctk.CTkButton(
                        card, text="✓ Отправлен", width=120, height=36,
                        fg_color=CLR_SUCCESS, hover_color="#009624",
                        text_color="black", corner_radius=8,
                        font=ctk.CTkFont(size=12, weight="bold"),
                        command=lambda pid=pack_id: self._toggle_pack_sent(pid)
                    ).pack(side="right", padx=12, pady=10)

    def _toggle_pack_sent(self, pack_id):
        if not self.current_chat: return
        if self.is_pack_sent(pack_id, self.current_chat):
            self.unmark_pack_sent(pack_id, self.current_chat)
        else:
            self.mark_pack_sent(pack_id, self.current_chat)
        self._render_pack_cards()
        self.refresh_chats_ui()


    # ─────────────────────────────────────────────────────
    #  PACK MANAGER  (3-column window)
    # ─────────────────────────────────────────────────────
    def open_pack_manager(self):
        win = ctk.CTkToplevel(self)
        win.title("📦  Pack Manager")
        win.geometry("960x660")
        win.configure(fg_color=CLR_BG)
        win.grab_set(); win.lift()

        hdr = ctk.CTkFrame(win, fg_color=CLR_CARD, corner_radius=0, height=58)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="📦  PACK MANAGER",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=CLR_CYAN).pack(side="left", padx=20, pady=14)

        auto_clr = CLR_ACCENT if HAS_MUTAGEN else "#2A2A4A"
        auto_tip = "🎨  Авто по обложке" if HAS_MUTAGEN else "🎨  Авто (нужен mutagen)"
        ctk.CTkButton(hdr, text=auto_tip, height=34, corner_radius=8,
                      fg_color=auto_clr, hover_color=CLR_ACCENT2 if HAS_MUTAGEN else "#2A2A4A",
                      font=ctk.CTkFont(size=12, weight="bold"),
                      command=lambda: self._do_auto_detect(win) if HAS_MUTAGEN else None
                      ).pack(side="right", padx=12, pady=10)

        cols = ctk.CTkFrame(win, fg_color="transparent")
        cols.pack(fill="both", expand=True, padx=14, pady=12)
        cols.columnconfigure(0, weight=3, minsize=220)
        cols.columnconfigure(1, weight=4, minsize=280)
        cols.columnconfigure(2, weight=4, minsize=300)
        cols.rowconfigure(0, weight=1)

        # ── Left: pack list ──
        left = ctk.CTkFrame(cols, fg_color=CLR_PANEL, corner_radius=12)
        left.grid(row=0, column=0, sticky="nsew", padx=(0,6))
        ctk.CTkLabel(left, text="ПАКИ",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=CLR_MUTED).pack(pady=(12,4), padx=12, anchor="w")
        pack_scroll = ctk.CTkScrollableFrame(left, fg_color="transparent")
        pack_scroll.pack(fill="both", expand=True, padx=6, pady=(0,6))
        create_row = ctk.CTkFrame(left, fg_color=CLR_CARD, corner_radius=10, height=46)
        create_row.pack(fill="x", padx=6, pady=6); create_row.pack_propagate(False)
        name_entry = ctk.CTkEntry(create_row, placeholder_text="Название нового пака…",
                                  fg_color="transparent", border_width=0,
                                  font=ctk.CTkFont(size=12), text_color=CLR_TEXT)
        name_entry.pack(side="left", fill="both", expand=True, padx=10)

        # ── Middle: pack files ──
        mid = ctk.CTkFrame(cols, fg_color=CLR_PANEL, corner_radius=12)
        mid.grid(row=0, column=1, sticky="nsew", padx=6)
        mid_hdr_lbl = ctk.CTkLabel(mid, text="ФАЙЛЫ В ПАКЕ",
                     font=ctk.CTkFont(size=11, weight="bold"), text_color=CLR_MUTED)
        mid_hdr_lbl.pack(pady=(12,4), padx=12, anchor="w")
        mid_scroll = ctk.CTkScrollableFrame(mid, fg_color="transparent")
        mid_scroll.pack(fill="both", expand=True, padx=6, pady=(0,6))

        # ── Right: file browser ──
        right = ctk.CTkFrame(cols, fg_color=CLR_PANEL, corner_radius=12)
        right.grid(row=0, column=2, sticky="nsew", padx=(6,0))
        ctk.CTkLabel(right, text="ВСЕ ФАЙЛЫ  (+ добавить в пак)",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=CLR_MUTED).pack(pady=(12,4), padx=12, anchor="w")

        # Search bar for file browser
        search_row = ctk.CTkFrame(right, fg_color=CLR_CARD, corner_radius=9, height=36)
        search_row.pack(fill="x", padx=8, pady=(0,6)); search_row.pack_propagate(False)
        file_search_var = ctk.StringVar()
        file_search_entry = ctk.CTkEntry(
            search_row, placeholder_text="🔍 Поиск по названию…",
            textvariable=file_search_var,
            fg_color="transparent", border_width=0,
            font=ctk.CTkFont(size=11), text_color=CLR_TEXT)
        file_search_entry.pack(fill="both", expand=True, padx=8)

        right_scroll = ctk.CTkScrollableFrame(right, fg_color="transparent")
        right_scroll.pack(fill="both", expand=True, padx=6, pady=(0,6))

        selected_pack = [None]

        def refresh_pack_files():
            for w in mid_scroll.winfo_children(): w.destroy()
            pid = selected_pack[0]
            if not pid or pid not in self.packs:
                ctk.CTkLabel(mid_scroll, text="← Выбери пак",
                             text_color=CLR_MUTED).pack(pady=20)
                return
            files = self.packs[pid].get("files", [])
            mid_hdr_lbl.configure(text=f"ФАЙЛЫ: {self.packs[pid]['name']}  ({len(files)})")
            if not files:
                ctk.CTkLabel(mid_scroll, text="Пак пустой\nДобавь файлы справа →",
                             text_color=CLR_MUTED, justify="center").pack(pady=20)
                return
            for fname in list(files):
                row = ctk.CTkFrame(mid_scroll, fg_color=CLR_CARD, corner_radius=7)
                row.pack(fill="x", pady=2, padx=2)
                disp = fname if len(fname) < 42 else fname[:39] + "…"
                ctk.CTkLabel(row, text=disp, font=ctk.CTkFont(size=11),
                             text_color=CLR_TEXT, anchor="w").pack(
                    side="left", padx=8, pady=6, fill="x", expand=True)
                def _rm(fn=fname, p=pid):
                    if p in self.packs:
                        try: self.packs[p]["files"].remove(fn)
                        except ValueError: pass
                        self.save_packs(); refresh_pack_files()
                ctk.CTkButton(row, text="×", width=24, height=24,
                              fg_color="transparent", text_color=CLR_MAGENTA,
                              hover_color=CLR_CARD_HOV, command=_rm).pack(side="right", padx=4)

        def refresh_file_browser(*_):
            for w in right_scroll.winfo_children(): w.destroy()
            q = file_search_var.get().lower().strip()
            all_folders = set()
            for folders in self.local_folders.values():
                all_folders.update(folders)
            found_any = False
            for folder in sorted(all_folders):
                if not os.path.exists(folder): continue
                files = [f for f in sorted(os.listdir(folder))
                         if f.lower().endswith(SUPPORTED)
                         and (not q or q in f.lower())]
                if not files: continue
                found_any = True
                ctk.CTkLabel(right_scroll,
                             text=f"📂 {os.path.basename(folder)}",
                             font=ctk.CTkFont(size=10, weight="bold"),
                             text_color=CLR_MUTED).pack(anchor="w", padx=6, pady=(8,2))
                for fname in files:
                    row = ctk.CTkFrame(right_scroll, fg_color=CLR_CARD, corner_radius=7)
                    row.pack(fill="x", pady=1, padx=2)
                    disp = fname if len(fname) < 36 else fname[:33] + "…"
                    ctk.CTkLabel(row, text=disp, font=ctk.CTkFont(size=10),
                                 text_color=CLR_TEXT, anchor="w").pack(
                        side="left", padx=8, pady=5, fill="x", expand=True)
                    def _add(fn=fname):
                        pid = selected_pack[0]
                        if not pid:
                            self.set_status("← Сначала выбери пак", CLR_WARN); return
                        if pid not in self.packs: return
                        if fn not in self.packs[pid]["files"]:
                            self.packs[pid]["files"].append(fn)
                            self.save_packs(); refresh_pack_files()
                    ctk.CTkButton(row, text="+", width=26, height=26,
                                  fg_color="transparent", text_color=CLR_GREEN,
                                  hover_color=CLR_CARD_HOV,
                                  font=ctk.CTkFont(size=14, weight="bold"),
                                  command=_add).pack(side="right", padx=4)
            if not found_any:
                ctk.CTkLabel(right_scroll,
                             text="Нет файлов\nДобавь папки через 📁 в главном окне",
                             text_color=CLR_MUTED, justify="center").pack(pady=30)

        def select_pack(pid):
            selected_pack[0] = pid
            refresh_pack_list(); refresh_pack_files()

        def refresh_pack_list():
            for w in pack_scroll.winfo_children(): w.destroy()
            if not self.packs:
                ctk.CTkLabel(pack_scroll, text="Нет паков\nВведи имя ниже и нажми +",
                             text_color=CLR_MUTED, justify="center").pack(pady=20)
                return
            for pid, pack in self.packs.items():
                active = (selected_pack[0] == pid)
                color  = pack.get("color", CLR_ACCENT)
                row = ctk.CTkFrame(pack_scroll,
                                   fg_color=CLR_ACCENT if active else CLR_CARD,
                                   corner_radius=9)
                row.pack(fill="x", pady=3, padx=2)

                # Clickable color dot → opens color picker
                dot_c = tk.Canvas(row, width=18, height=18,
                                  bg=CLR_ACCENT if active else CLR_CARD,
                                  highlightthickness=0, cursor="hand2")
                dot_c.create_oval(2,2,16,16, fill=color, outline="white", width=1,
                                  tags="dot")
                dot_c.pack(side="left", padx=(8,4), pady=8)

                def _pick_color(p=pid, c=dot_c):
                    self._open_color_picker(win, p, lambda: (refresh_pack_list(), refresh_pack_files()))
                dot_c.bind("<Button-1>", lambda e, p=pid: _pick_color(p))

                label = f"{pack['name']}  ({len(pack.get('files',[]))})"
                ctk.CTkButton(
                    row, text=label, fg_color="transparent", hover=False,
                    anchor="w", font=ctk.CTkFont(size=12, weight="bold"),
                    text_color=CLR_TEXT, command=lambda p=pid: select_pack(p)
                ).pack(side="left", fill="x", expand=True, pady=6)
                def _del(p=pid):
                    self.delete_pack(p)
                    if selected_pack[0] == p: selected_pack[0] = None
                    refresh_pack_list(); refresh_pack_files()
                ctk.CTkButton(row, text="×", width=24, height=24,
                              fg_color="transparent", text_color=CLR_MAGENTA,
                              hover_color=CLR_CARD_HOV, command=_del).pack(side="right", padx=6)

        def create_new_pack():
            name = name_entry.get().strip() or f"Pack #{len(self.packs)+1}"
            pid  = self.create_pack(name)
            selected_pack[0] = pid
            name_entry.delete(0, "end")
            refresh_pack_list(); refresh_pack_files()

        name_entry.bind("<Return>", lambda e: create_new_pack())
        ctk.CTkButton(create_row, text="+", width=36, height=36, corner_radius=8,
                      fg_color=CLR_ACCENT, hover_color=CLR_ACCENT2,
                      font=ctk.CTkFont(size=16, weight="bold"),
                      command=create_new_pack).pack(side="right", padx=6)

        file_search_var.trace_add("write", refresh_file_browser)
        refresh_pack_list(); refresh_pack_files(); refresh_file_browser()

    # ─── auto detect by cover ───
    def _do_auto_detect(self, parent_win):
        prog_win = ctk.CTkToplevel(parent_win)
        prog_win.title("Авто-определение паков…")
        prog_win.geometry("400x150")
        prog_win.configure(fg_color=CLR_BG)
        prog_win.grab_set()
        lbl = ctk.CTkLabel(prog_win, text="Сканирование файлов…",
                           font=ctk.CTkFont(size=13), text_color=CLR_TEXT)
        lbl.pack(pady=(28,8))
        bar = ctk.CTkProgressBar(prog_win, width=340, fg_color=CLR_CARD,
                                  progress_color=CLR_ACCENT)
        bar.pack(); bar.set(0)

        def _run():
            def _cb(i, total):
                pct = i / total if total else 0
                self.after(0, lambda: bar.set(pct))
                self.after(0, lambda i=i, t=total: lbl.configure(text=f"Сканирование {i}/{t}…"))
            groups, _ = self.auto_detect_packs_by_cover(progress_cb=_cb)
            def _done():
                prog_win.destroy()
                created = 0
                for i, (_, paths) in enumerate(groups.items()):
                    if len(paths) < 2: continue
                    names = [os.path.basename(p) for p in paths]
                    color = PACK_COLORS[i % len(PACK_COLORS)]
                    self.create_pack(f"Pack #{len(self.packs)+1} (auto)", files=names, color=color)
                    created += 1
                parent_win.lift()
                msg = (f"✓ Создано {created} паков по обложке" if created
                       else "Не найдено групп с одинаковой обложкой")
                self.set_status(msg, CLR_GREEN if created else CLR_WARN)
                parent_win.destroy()
                self.after(200, self.open_pack_manager)
            self.after(0, _done)
        threading.Thread(target=_run, daemon=True).start()


    # ─────────────────────────────────────────────────────
    #  PACK DASHBOARD  (grid: packs × artists)
    # ─────────────────────────────────────────────────────
    def open_pack_dashboard(self):
        win = ctk.CTkToplevel(self)
        win.title("📊  Pack Dashboard")
        win.geometry("1100x640")
        win.configure(fg_color=CLR_BG)
        win.lift()

        ctk.CTkLabel(win, text="📊  PACK DASHBOARD",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=CLR_CYAN).pack(pady=(18,2), padx=20, anchor="w")
        ctk.CTkLabel(
            win,
            text="Строки = артисты  ·  Столбцы = паки  ·  ✓ зелёный = отправлен  ·  — серый = нет",
            font=ctk.CTkFont(size=11), text_color=CLR_MUTED).pack(padx=20, anchor="w")

        if not self.packs:
            ctk.CTkLabel(win, text="Нет паков. Создай паки в Pack Manager (📦).",
                         text_color=CLR_MUTED, font=ctk.CTkFont(size=13)).pack(pady=60)
            return
        if not self.chats:
            ctk.CTkLabel(win, text="Нет артистов.",
                         text_color=CLR_MUTED, font=ctk.CTkFont(size=13)).pack(pady=60)
            return

        outer = ctk.CTkFrame(win, fg_color=CLR_PANEL, corner_radius=12)
        outer.pack(fill="both", expand=True, padx=20, pady=14)

        canvas = tk.Canvas(outer, bg=CLR_PANEL, highlightthickness=0)
        v_bar  = tk.Scrollbar(outer, orient="vertical",   command=canvas.yview)
        h_bar  = tk.Scrollbar(outer, orient="horizontal", command=canvas.xview)
        canvas.configure(yscrollcommand=v_bar.set, xscrollcommand=h_bar.set)
        h_bar.pack(side="bottom", fill="x")
        v_bar.pack(side="right",  fill="y")
        canvas.pack(side="left",  fill="both", expand=True)

        grid_frame = tk.Frame(canvas, bg=CLR_PANEL)
        canvas.create_window((0,0), window=grid_frame, anchor="nw")

        artists = list(self.chats.items())
        packs   = list(self.packs.items())
        FONT_SM = ("Segoe UI", 10, "bold")
        FONT_N  = ("Segoe UI", 10)

        # ── VERTICAL layout: rows = artists, columns = packs ──

        # Top-left blank corner
        tk.Label(grid_frame, text="АРТИСТ", width=22,
                 bg=CLR_CARD, fg=CLR_MUTED, font=FONT_SM,
                 relief="flat", padx=8, pady=8).grid(row=0, column=0, padx=1, pady=1, sticky="nsew")

        # Header: pack names as columns
        for col, (pid, pack) in enumerate(packs, start=1):
            color  = pack.get("color", CLR_ACCENT)
            pname  = pack['name']
            short  = pname if len(pname) < 13 else pname[:11] + "…"

            hdr_f = tk.Frame(grid_frame, bg=CLR_CARD, width=110)
            hdr_f.grid(row=0, column=col, padx=1, pady=1, sticky="nsew")
            hdr_f.pack_propagate(False)
            # Color dot at top
            dot_cv = tk.Canvas(hdr_f, width=10, height=10, bg=CLR_CARD, highlightthickness=0)
            dot_cv.create_oval(1,1,9,9, fill=color, outline="")
            dot_cv.pack(pady=(6,2))
            tk.Label(hdr_f, text=short, bg=CLR_CARD, fg=CLR_TEXT,
                     font=FONT_SM, anchor="center", wraplength=100, justify="center",
                     pady=4).pack()

        # Artist rows
        for row, (raw, data) in enumerate(artists, start=1):
            row_bg = CLR_CARD if row % 2 == 0 else "#10112A"
            name   = data['display']
            short_a = name if len(name) < 20 else name[:18] + "…"

            # Artist name cell
            tk.Label(grid_frame, text=short_a, width=22,
                     bg=row_bg, fg=CLR_TEXT, font=FONT_SM,
                     anchor="w", padx=10, pady=8).grid(
                row=row, column=0, padx=1, pady=1, sticky="nsew")

            # Pack cells
            for col, (pid, _) in enumerate(packs, start=1):
                sent    = self.is_pack_sent(pid, raw)
                date    = self.sent_packs.get(raw, {}).get(pid, "")
                cell_bg = "#0B1C0B" if sent else row_bg
                txt     = f"✓ {date}" if sent else "—"
                tc      = CLR_GREEN  if sent else CLR_MUTED
                tk.Label(grid_frame, text=txt, width=14,
                         bg=cell_bg, fg=tc, font=FONT_N,
                         anchor="center", pady=8).grid(
                    row=row, column=col, padx=1, pady=1, sticky="nsew")

        def _on_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
        grid_frame.bind("<Configure>", _on_configure)

        def _on_mousewheel(e):
            canvas.yview_scroll(int(-1*(e.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        win.protocol("WM_DELETE_WINDOW", lambda: (
            canvas.unbind_all("<MouseWheel>"), win.destroy()))

    # ─────────────────────────────────────────────────────
    #  PLAYER
    # ─────────────────────────────────────────────────────
    def _play_by_idx(self, idx, path):
        self.current_path_idx = idx
        self.play_audio(path)

    def play_audio(self, path):
        if self.current_playing == path:
            self.toggle_pause(); return
        self.current_playing  = path
        self.is_paused        = False
        self.seek_start_time  = 0.0
        self.current_duration = 0.0
        self._was_busy        = False
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
            pygame.mixer.music.set_volume(self.volume)
        except Exception as e:
            self.set_status(f"Playback error: {e}", CLR_WARN); return
        name  = os.path.basename(path)
        short = name if len(name) < 58 else name[:55] + "…"
        self.lbl_now_playing.configure(text=f"▶  {short}", text_color=CLR_CYAN)
        self.lbl_time.configure(text_color=CLR_CYAN)
        self.btn_play_main.configure(text="⏸")
        self.slider_progress.configure(to=100)
        self.slider_progress.set(0)
        def _get_dur():
            try:
                snd = pygame.mixer.Sound(path)
                dur = snd.get_length()
                del snd
                self.after(0, lambda: self._set_duration(dur))
            except: pass
        threading.Thread(target=_get_dur, daemon=True).start()
        self.update_ui_buttons()

    def _set_duration(self, dur):
        self.current_duration = dur
        if dur > 0: self.slider_progress.configure(to=dur)

    def stop_audio(self):
        pygame.mixer.music.stop()
        prev = self._last_playing_name
        self.current_playing  = None
        self.current_path_idx = -1
        self.is_paused        = False
        self.seek_start_time  = 0.0
        self.current_duration = 0.0
        self._was_busy        = False
        self._last_playing_name = None
        if prev and prev in self.playing_buttons:
            try: self.playing_buttons[prev].configure(
                text="▶", fg_color=CLR_PANEL, text_color=CLR_CYAN)
            except: pass
        self.slider_progress.set(0)
        self.lbl_now_playing.configure(text="●  READY TO PLAY", text_color=CLR_MUTED)
        self.lbl_time.configure(text="0:00 / 0:00", text_color=CLR_MUTED)
        self.btn_play_main.configure(text="▶")

    def toggle_pause(self):
        if not self.current_playing: return
        if self.is_paused:
            pygame.mixer.music.unpause()
            self.is_paused = False
            self.btn_play_main.configure(text="⏸")
        else:
            pygame.mixer.music.pause()
            self.is_paused = True
            self.btn_play_main.configure(text="▶")
        self.update_ui_buttons()

    def play_next(self):
        n = len(self.missing_files_data)
        if not n: return
        idx = random.randint(0,n-1) if self.shuffle_mode else (self.current_path_idx+1) % n
        self.current_path_idx = idx
        self.play_audio(self.missing_files_data[idx]['path'])

    def play_prev(self):
        n = len(self.missing_files_data)
        if not n: return
        idx = max(0, self.current_path_idx - 1)
        self.current_path_idx = idx
        self.play_audio(self.missing_files_data[idx]['path'])

    def toggle_shuffle(self):
        self.shuffle_mode = not self.shuffle_mode
        self.btn_shuffle.configure(
            fg_color=CLR_ACCENT if self.shuffle_mode else CLR_CARD,
            text_color=CLR_TEXT  if self.shuffle_mode else CLR_MUTED)

    def update_ui_buttons(self):
        cur_name  = os.path.basename(self.current_playing) if self.current_playing else None
        prev_name = self._last_playing_name
        if prev_name and prev_name != cur_name:
            btn = self.playing_buttons.get(prev_name)
            if btn:
                try: btn.configure(text="▶", fg_color=CLR_PANEL, text_color=CLR_CYAN)
                except: pass
        if cur_name:
            btn = self.playing_buttons.get(cur_name)
            if btn:
                try:
                    if not self.is_paused:
                        btn.configure(text="⏸", fg_color=CLR_CYAN, text_color="black")
                    else:
                        btn.configure(text="▶", fg_color=CLR_PANEL, text_color=CLR_CYAN)
                except: pass
        elif prev_name:
            btn = self.playing_buttons.get(prev_name)
            if btn:
                try: btn.configure(text="▶", fg_color=CLR_PANEL, text_color=CLR_CYAN)
                except: pass
        self._last_playing_name = cur_name

    def set_volume(self, v):
        self.volume = float(v)
        pygame.mixer.music.set_volume(self.volume)
        icon = "🔇" if self.volume < 0.01 else ("🔈" if self.volume < 0.45 else "🔊")
        self.lbl_vol_icon.configure(text=icon)

    def set_status(self, text, color=None):
        self.lbl_status.configure(text=text, text_color=color or CLR_MUTED)
        if color in (CLR_GREEN, CLR_SUCCESS):
            self.after(4000, lambda: self.lbl_status.configure(text=""))


    # ─────────────────────────────────────────────────────
    #  ANIMATION LOOP
    # ─────────────────────────────────────────────────────
    def _animate(self):
        try:
            busy    = pygame.mixer.music.get_busy()
            playing = busy and not self.is_paused

            if self._was_busy and not busy and \
               self.current_playing and not self.is_paused and not self.is_seeking:
                self.after(200, self.play_next)
            self._was_busy = busy

            if self.vis_canvas.winfo_exists():
                h = max(self.vis_canvas.winfo_height(), 40)
                w = max(self.vis_canvas.winfo_width(), 140)
                self._bar_tick += 1
                if playing and self._bar_tick % 2 == 0:
                    for i in range(BAR_COUNT):
                        cb = 1.0 - abs(i - BAR_COUNT/2) / (BAR_COUNT/2) * 0.4
                        self._bar_tgt[i] = random.randint(4, int((h-6)*cb))
                elif not playing:
                    for i in range(BAR_COUNT):
                        self._bar_tgt[i] = 4
                for i in range(BAR_COUNT):
                    self._bar_cur[i] += (self._bar_tgt[i] - self._bar_cur[i]) * 0.28

                bar_w   = 4
                gap     = 2
                total_w = BAR_COUNT * (bar_w + gap) - gap
                x0      = max(0, (w - total_w) // 2)

                if len(self._vis_bars_ids) != BAR_COUNT or \
                   self._vis_w_cached != w or self._vis_h_cached != h:
                    self.vis_canvas.delete("all")
                    self._vis_bars_ids = [
                        self.vis_canvas.create_rectangle(0,0,1,1,outline="")
                        for _ in range(BAR_COUNT)]
                    self._vis_w_cached = w
                    self._vis_h_cached = h

                for i, bid in enumerate(self._vis_bars_ids):
                    bh  = max(4, int(self._bar_cur[i]))
                    bx  = x0 + i * (bar_w + gap)
                    by  = h - bh
                    t   = i / (BAR_COUNT - 1)
                    r   = int(0x00 + t * (0xFF - 0x00))
                    g   = int(0xD0 - t * (0xD0 - 0x2D))
                    b   = int(0xFF - t * (0xFF - 0x78))
                    clr = f"#{r:02X}{g:02X}{b:02X}"
                    self.vis_canvas.coords(bid, bx, by, bx+bar_w, h)
                    self.vis_canvas.itemconfig(bid, fill=clr)

            if not self.is_seeking and self.current_playing and not self.is_paused:
                pos = pygame.mixer.music.get_pos() / 1000.0
                if pos >= 0:
                    elapsed = self.seek_start_time + pos
                    if self.current_duration > 0:
                        self.slider_progress.set(min(elapsed, self.current_duration))
                    self.lbl_time.configure(
                        text=f"{self._fmt_time(elapsed)} / {self._fmt_time(self.current_duration)}")
        except Exception:
            pass
        self.after(ANIM_MS, self._animate)

    # ─────────────────────────────────────────────────────
    #  TELEGRAM
    # ─────────────────────────────────────────────────────
    async def connect_tg(self):
        try:
            await self.client.connect()
            if await self.client.is_user_authorized():
                self.after(0, lambda: (
                    setattr(self, 'is_connected', True),
                    self.dot_canvas.itemconfig(self._tg_dot, fill=CLR_SUCCESS),
                    self.btn_tg_connect.configure(
                        text="✓ OK", fg_color=CLR_SUCCESS,
                        text_color="black", state="disabled"),
                    self.set_status("Telegram connected", CLR_GREEN)
                ))
        except Exception as e:
            self.after(0, lambda: (
                self.dot_canvas.itemconfig(self._tg_dot, fill=CLR_MAGENTA),
                self.set_status(f"TG ошибка: {e}", CLR_WARN)
            ))

    def open_tg_auth(self):
        win = ctk.CTkToplevel(self)
        win.title("Telegram — Авторизация")
        win.geometry("440x480"); win.configure(fg_color=CLR_BG)
        win.grab_set(); win.lift(); win.resizable(False, False)
        ctk.CTkLabel(win, text="🔐  TELEGRAM LOGIN",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=CLR_CYAN).pack(pady=(18,2))
        ctk.CTkLabel(win,
            text="Свой API ID и Hash — на my.telegram.org → App configuration",
            font=ctk.CTkFont(size=10), text_color=CLR_MUTED, wraplength=400
        ).pack(pady=(0,8))
        _e_kw = dict(width=320, height=38, fg_color=CLR_CARD,
                     border_color=CLR_BORDER, text_color=CLR_TEXT,
                     font=ctk.CTkFont(size=13))

        def _row(lbl, ph, default=""):
            ctk.CTkLabel(win, text=lbl, font=ctk.CTkFont(size=11),
                         text_color=CLR_TEXT, anchor="w").pack(anchor="w", padx=60)
            e = ctk.CTkEntry(win, placeholder_text=ph, **_e_kw)
            if default: e.insert(0, default)
            e.pack(pady=(2,8)); return e

        api_id_e   = _row("API ID:",   "12345678", str(API_ID))
        api_hash_e = _row("API Hash:", "0123abcd…", API_HASH)
        phone_e    = _row("Телефон:",  "+7XXXXXXXXXX", PHONE)
        code_e     = ctk.CTkEntry(win, placeholder_text="Код из Telegram…", **_e_kw)
        pass2fa_e  = ctk.CTkEntry(win, placeholder_text="Пароль 2FA…", show="●", **_e_kw)

        status_lbl = ctk.CTkLabel(win, text="", font=ctk.CTkFont(size=11),
                                   text_color=CLR_MUTED, wraplength=400)
        status_lbl.pack(pady=(0,4))

        action_btn = [None]
        _ph_hash   = [None]

        def _st(txt, clr=CLR_MUTED):
            status_lbl.configure(text=txt, text_color=clr)

        def _finish():
            self.is_connected = True
            self.dot_canvas.itemconfig(self._tg_dot, fill=CLR_SUCCESS)
            self.btn_tg_connect.configure(text="✓ OK", fg_color=CLR_SUCCESS,
                                           text_color="black", state="disabled")
            self.set_status("Telegram connected", CLR_GREEN)
            win.destroy()

        def _step_2fa():
            pwd = pass2fa_e.get().strip()
            if not pwd: _st("Введи пароль 2FA", CLR_WARN); return
            action_btn[0].configure(state="disabled", text="Проверяем…")
            async def _check():
                try:
                    await self.client.sign_in(password=pwd)
                    self.after(0, _finish)
                except Exception as exc:
                    err = str(exc)
                    self.after(0, lambda: (
                        action_btn[0].configure(state="normal", text="ВОЙТИ"),
                        _st(f"Неверный пароль: {err}", CLR_WARN)))
            asyncio.run_coroutine_threadsafe(_check(), self.loop)

        def _step_sign_in():
            code  = code_e.get().strip()
            phone = phone_e.get().strip()
            if not code: _st("Введи код из Telegram", CLR_WARN); return
            action_btn[0].configure(state="disabled", text="Проверяем…")
            _st("Авторизация…", CLR_YELLOW)
            async def _sign():
                try:
                    await self.client.sign_in(phone, code, phone_code_hash=_ph_hash[0])
                    self.after(0, _finish)
                except Exception as exc:
                    from telethon.errors import SessionPasswordNeededError
                    if isinstance(exc, SessionPasswordNeededError):
                        def _ask_2fa():
                            code_e.configure(state="disabled")
                            ctk.CTkLabel(win, text="Пароль 2FA:",
                                         font=ctk.CTkFont(size=11),
                                         text_color=CLR_TEXT, anchor="w").pack(anchor="w", padx=60)
                            pass2fa_e.pack(pady=(2,8))
                            win.geometry("440x560")
                            _st("Требуется пароль 2FA", CLR_YELLOW)
                            action_btn[0].configure(state="normal", text="ВОЙТИ",
                                                    command=_step_2fa)
                        self.after(0, _ask_2fa)
                    else:
                        err = str(exc)
                        self.after(0, lambda: (
                            action_btn[0].configure(state="normal", text="ПОДТВЕРДИТЬ"),
                            _st(f"Ошибка: {err}", CLR_WARN)))
            asyncio.run_coroutine_threadsafe(_sign(), self.loop)

        def _step_send_code():
            raw_id   = api_id_e.get().strip()
            raw_hash = api_hash_e.get().strip()
            phone    = phone_e.get().strip()
            if not raw_id.isdigit():        _st("API ID должен быть числом", CLR_WARN); return
            if len(raw_hash) < 20:          _st("API Hash слишком короткий", CLR_WARN); return
            if not phone.startswith("+"):   _st("Номер должен начинаться с +", CLR_WARN); return
            action_btn[0].configure(state="disabled", text="Отправка…")
            _st("Подключаемся к Telegram…", CLR_YELLOW)
            async def _send():
                try:
                    nc = TelegramClient(SESSION_NAME, int(raw_id), raw_hash)
                    await nc.connect()
                    r = await nc.send_code_request(phone)
                    _ph_hash[0] = r.phone_code_hash
                    self.client = nc
                    def _ok():
                        phone_e.configure(state="disabled")
                        api_id_e.configure(state="disabled")
                        api_hash_e.configure(state="disabled")
                        code_e.pack(pady=(2,8))
                        _st("✓ Код отправлен! Введи его выше.", CLR_GREEN)
                        action_btn[0].configure(state="normal", text="ПОДТВЕРДИТЬ",
                                                command=_step_sign_in)
                    self.after(0, _ok)
                except Exception as exc:
                    err = str(exc)
                    self.after(0, lambda: (
                        action_btn[0].configure(state="normal", text="ОТПРАВИТЬ КОД"),
                        _st(f"Ошибка: {err}", CLR_WARN)))
            asyncio.run_coroutine_threadsafe(_send(), self.loop)

        btn = ctk.CTkButton(win, text="ОТПРАВИТЬ КОД", height=44, width=320,
                             fg_color=CLR_ACCENT, hover_color=CLR_ACCENT2,
                             font=ctk.CTkFont(size=13, weight="bold"),
                             corner_radius=12, command=_step_send_code)
        btn.pack(pady=8)
        action_btn[0] = btn
        ctk.CTkButton(win, text="Отмена", height=28, width=120,
                       fg_color="transparent", text_color=CLR_MUTED,
                       hover_color=CLR_CARD, corner_radius=8,
                       command=win.destroy).pack(pady=(2,0))

    # ─────────────────────────────────────────────────────
    #  CHAT MANAGEMENT
    # ─────────────────────────────────────────────────────
    def add_chat(self):
        raw = self.chat_entry.get().strip()
        if raw and raw not in self.chats:
            self.chats[raw] = {"display": raw, "real_id": raw}
            self.save_chats(); self.refresh_chats_ui()
            asyncio.run_coroutine_threadsafe(self.resolve_id(raw), self.loop)
        self.chat_entry.delete(0, "end")

    async def resolve_id(self, raw):
        try:
            entity = await self.client.get_entity(raw)
            self.chats[raw]["display"] = utils.get_display_name(entity) or raw
            self.chats[raw]["real_id"] = str(entity.id)
            self.save_chats()
            self.after(0, self.refresh_chats_ui)
        except: pass

    def _on_window_restore(self, event=None):
        if event and str(event.widget) != ".": return
        if self.current_chat:
            self.select_chat(self.current_chat, force_reload=True)

    def refresh_chats_ui(self):
        for w in self.chat_list_scroll.winfo_children(): w.destroy()
        if not self.chats:
            ctk.CTkLabel(self.chat_list_scroll,
                         text="Добавь артиста выше,\nчтобы начать",
                         text_color=CLR_MUTED, font=ctk.CTkFont(size=12),
                         justify="center").pack(pady=30)
            return
        for raw, data in self.chats.items():
            active = (self.current_chat == raw)
            f = ctk.CTkFrame(self.chat_list_scroll,
                              fg_color=CLR_ACCENT if active else CLR_CARD,
                              corner_radius=11)
            f.pack(fill="x", pady=4, padx=4)
            if not active:
                def _e(ev, fr=f): fr.configure(fg_color=CLR_CARD_HOV)
                def _l(ev, fr=f): fr.configure(fg_color=CLR_CARD)
                f.bind("<Enter>", _e); f.bind("<Leave>", _l)

            unsent = sum(1 for pid in self.packs if not self.is_pack_sent(pid, raw))

            inner = ctk.CTkFrame(f, fg_color="transparent")
            inner.pack(side="left", fill="x", expand=True, padx=10, pady=8)

            ctk.CTkButton(
                inner, text=data['display'], anchor="w",
                fg_color="transparent", hover=False,
                font=ctk.CTkFont(size=13, weight="bold"), text_color=CLR_TEXT,
                command=lambda r=raw: self.select_chat(r)
            ).pack(anchor="w")

            if unsent > 0:
                ctk.CTkLabel(
                    inner, text=f"  {unsent} пак{'а' if unsent in (2,3,4) else 'ов'} не отправлено",
                    font=ctk.CTkFont(size=10), text_color=CLR_WARN, anchor="w"
                ).pack(anchor="w")

            ctk.CTkButton(
                f, text="×", width=28, height=28,
                fg_color="transparent", text_color=CLR_MAGENTA,
                hover_color=CLR_CARD_HOV,
                font=ctk.CTkFont(size=14, weight="bold"),
                command=lambda r=raw: self.delete_chat(r)
            ).pack(side="right", padx=6)

    def select_chat(self, raw, force_reload=False):
        if raw is None: return
        if self.current_chat == raw and not force_reload: return
        if self.current_chat != raw: self.active_folder = None
        self.current_chat = raw
        self.refresh_chats_ui()
        for w in self.scroll_sent.winfo_children():  w.destroy()
        for w in self.scroll_local.winfo_children(): w.destroy()
        self._update_folder_tabs()
        ctk.CTkLabel(self.scroll_local, text="⏳  Загрузка…",
                     text_color=CLR_MUTED, font=ctk.CTkFont(size=12)).pack(pady=35)
        threading.Thread(target=self._load_files_task, args=(raw,), daemon=True).start()

    def _load_files_task(self, raw):
        real_id  = self.chats[raw].get("real_id", raw)
        all_sent = self.tracked_files.get(real_id, [])
        seen, sent = set(), []
        for f in all_sent:
            if f['name'] not in seen:
                seen.add(f['name']); sent.append(f)

        search = self.search_entry.get().lower()
        if search: sent = [f for f in sent if search in f['name'].lower()]

        folders = self.local_folders.get(raw, [])
        if self.active_folder is not None:
            folders = [self.active_folder] if self.active_folder in folders else []

        sent_lower = {f['name'].lower() for f in sent}
        missing = []
        for folder in folders:
            if not os.path.exists(folder): continue
            for fname in sorted(os.listdir(folder)):
                if not fname.lower().endswith(SUPPORTED): continue
                if fname.lower() in sent_lower: continue
                if search and search not in fname.lower(): continue
                fpath = os.path.join(folder, fname)
                try:   fsize = os.path.getsize(fpath)
                except: fsize = 0
                missing.append({"name": fname, "path": fpath, "size": fsize, "folder": folder})

        seen2, deduped = set(), []
        for m in missing:
            if m['name'] not in seen2:
                seen2.add(m['name']); deduped.append(m)

        self.after(0, lambda: self._render_files(sent, deduped))

    def scan_current(self):
        if not self.current_chat: return
        if not self.is_connected:
            self.set_status("Telegram не подключён", CLR_WARN); return
        self._is_scanning = True
        self.set_status("Сканирование…", CLR_YELLOW)
        asyncio.run_coroutine_threadsafe(self.scan_logic(self.current_chat), self.loop)

    async def scan_logic(self, raw):
        try:
            entity  = await self.client.get_entity(raw)
            chat_id = str(entity.id)
            fresh   = []
            async for msg in self.client.iter_messages(entity, limit=1000):
                if msg.media and hasattr(msg.media, 'document'):
                    doc = msg.media.document
                    if "audio" in doc.mime_type:
                        name = next(
                            (a.file_name for a in doc.attributes
                             if isinstance(a, DocumentAttributeFilename)), "unknown")
                        fresh.append({
                            "name": name,
                            "date": msg.date.strftime("%d.%m.%Y"),
                            "size": doc.size})
            seen, deduped = set(), []
            for f in fresh:
                if f['name'] not in seen:
                    seen.add(f['name']); deduped.append(f)
            self.tracked_files[chat_id] = deduped
            self.save_tracked()
            def _done():
                self._is_scanning = False
                self.set_status(f"✓ Загружено треков: {len(deduped)}", CLR_GREEN)
                self.select_chat(raw, force_reload=True)
            self.after(0, _done)
        except Exception as e:
            def _err():
                self._is_scanning = False
                self.set_status(f"Ошибка: {e}", CLR_WARN)
            self.after(0, _err)

    def delete_chat(self, raw):
        if raw not in self.chats: return
        del self.chats[raw]
        self.save_chats()
        if self.current_chat == raw:
            self.current_chat = None
            for w in self.scroll_sent.winfo_children():  w.destroy()
            for w in self.scroll_local.winfo_children(): w.destroy()
            self.lbl_sent_count.configure(text="")
            self.lbl_selected_count.configure(text="")
        self.refresh_chats_ui()

    # ─────────────────────────────────────────────────────
    #  SEND FILES
    # ─────────────────────────────────────────────────────
    def send_files(self):
        if not self.current_chat or not self.is_connected:
            self.set_status("Выбери чат и подключись к Telegram", CLR_WARN); return
        to_send = [m['path'] for m in self.missing_files_data
                   if self.missing_check_vars.get(m['name'])
                   and self.missing_check_vars[m['name']].get()]
        if not to_send:
            self.set_status("Нет выбранных файлов", CLR_WARN); return
        self.set_status(f"Подготовка {len(to_send)} файлов…", CLR_YELLOW)
        asyncio.run_coroutine_threadsafe(self.send_task(to_send), self.loop)

    async def send_task(self, paths):
        """Send files one-by-one with per-file status feedback."""
        try:
            entity  = await self.client.get_entity(self.current_chat)
            chat_id = str(entity.id)
            total   = len(paths)
            sent_ok = 0

            for i, p in enumerate(paths, start=1):
                fname = os.path.basename(p)
                short = fname if len(fname) < 40 else fname[:37] + "…"
                self.after(0, lambda s=short, i=i, t=total:
                    self.set_status(f"📤 {i}/{t}  {s}", CLR_YELLOW))
                try:
                    await self.client.send_file(entity, p, voice_note=False)
                    fsize = os.path.getsize(p)
                    existing = self.tracked_files.get(chat_id, [])
                    existing.append({
                        "name": fname,
                        "date": datetime.now().strftime("%d.%m.%Y"),
                        "size": fsize})
                    self.tracked_files[chat_id] = existing
                    self.save_tracked()
                    sent_ok += 1
                except Exception as file_err:
                    self.after(0, lambda e=str(file_err):
                        self.set_status(f"⚠ Ошибка файла: {e}", CLR_WARN))

            def _done():
                self.set_status(f"✅ Отправлено {sent_ok}/{total}", CLR_GREEN)
                self.select_chat(self.current_chat, force_reload=True)
            self.after(0, _done)

        except Exception as e:
            self.after(0, lambda: self.set_status(f"Ошибка отправки: {e}", CLR_WARN))


    # ─────────────────────────────────────────────────────
    #  COLOR PICKER  (popup grid of swatches)
    # ─────────────────────────────────────────────────────
    def _open_color_picker(self, parent, pack_id, on_done=None):
        pop = ctk.CTkToplevel(parent)
        pop.title("Выбери цвет пака")
        pop.geometry("320x210")
        pop.configure(fg_color=CLR_BG)
        pop.grab_set(); pop.lift()
        pop.resizable(False, False)

        ctk.CTkLabel(pop, text="🎨  Цвет пака",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=CLR_CYAN).pack(pady=(14,8))

        # Extended palette
        EXTENDED = [
            "#7C2EFF","#9B5FFF","#FF2D78","#FF6D8A",
            "#00D0FF","#00A8CC","#00E676","#00C853",
            "#FFD740","#FFA000","#FF6D00","#FF3D00",
            "#E040FB","#AA00FF","#00BCD4","#0097A7",
            "#69F0AE","#00BFA5","#F06292","#C2185B",
            "#4FC3F7","#0288D1","#AED581","#689F38",
        ]

        grid_f = ctk.CTkFrame(pop, fg_color="transparent")
        grid_f.pack()
        COLS = 8
        current_color = self.packs.get(pack_id, {}).get("color", EXTENDED[0])

        for i, clr in enumerate(EXTENDED):
            r, c = divmod(i, COLS)
            is_sel = (clr == current_color)
            size = 28
            cv = tk.Canvas(grid_f, width=size, height=size,
                           bg=CLR_BG, highlightthickness=0, cursor="hand2")
            cv.grid(row=r, column=c, padx=3, pady=3)
            outline = "white" if is_sel else CLR_BG
            ow      = 2       if is_sel else 1
            cv.create_oval(2, 2, size-2, size-2, fill=clr, outline=outline, width=ow)

            def _pick(chosen=clr):
                if pack_id in self.packs:
                    self.packs[pack_id]["color"] = chosen
                    self.save_packs()
                if on_done: on_done()
                pop.destroy()
            cv.bind("<Button-1>", lambda e, ch=clr: _pick(ch))

        ctk.CTkButton(pop, text="Отмена", height=28, width=100,
                       fg_color="transparent", text_color=CLR_MUTED,
                       hover_color=CLR_CARD, corner_radius=8,
                       command=pop.destroy).pack(pady=(10,0))

    # ─────────────────────────────────────────────────────
    #  BULK IMPORT  (paste list of @usernames or links)
    # ─────────────────────────────────────────────────────
    def open_bulk_import(self):
        win = ctk.CTkToplevel(self)
        win.title("📋  Массовый импорт аккаунтов")
        win.geometry("520x480")
        win.configure(fg_color=CLR_BG)
        win.grab_set(); win.lift()

        ctk.CTkLabel(win, text="📋  МАССОВЫЙ ИМПОРТ АРТИСТОВ",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=CLR_CYAN).pack(pady=(18,4))
        ctk.CTkLabel(
            win,
            text="Вставь список — один аккаунт на строку.\n"
                 "Форматы: @username  /  t.me/username  /  +79001234567",
            font=ctk.CTkFont(size=11), text_color=CLR_MUTED,
            justify="center").pack(pady=(0,10))

        txt = ctk.CTkTextbox(win, height=220, fg_color=CLR_CARD,
                              border_color=CLR_BORDER, border_width=1,
                              font=ctk.CTkFont(size=12), text_color=CLR_TEXT,
                              corner_radius=10)
        txt.pack(fill="x", padx=22, pady=(0,8))
        txt.insert("end", "@artist1\n@artist2\nt.me/artist3\n")

        status_lbl = ctk.CTkLabel(win, text="", font=ctk.CTkFont(size=11),
                                   text_color=CLR_MUTED)
        status_lbl.pack(pady=(0,4))

        prog = ctk.CTkProgressBar(win, width=460, fg_color=CLR_CARD,
                                   progress_color=CLR_ACCENT)
        prog.pack(pady=(0,8)); prog.set(0)

        def _do_import():
            raw_text = txt.get("1.0", "end").strip()
            lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
            if not lines:
                status_lbl.configure(text="Список пустой", text_color=CLR_WARN); return

            # Normalise handles
            handles = []
            for line in lines:
                h = line
                if h.startswith("https://t.me/"): h = "@" + h.split("/")[-1]
                elif h.startswith("t.me/"):        h = "@" + h.split("/")[-1]
                if not h.startswith("@") and not h.startswith("+"):
                    h = "@" + h
                handles.append(h)

            btn_import.configure(state="disabled", text="Импорт…")
            status_lbl.configure(text=f"Добавляем {len(handles)} аккаунтов…",
                                  text_color=CLR_YELLOW)

            added = 0
            for i, h in enumerate(handles):
                prog.set((i+1) / len(handles))
                if h not in self.chats:
                    self.chats[h] = {"display": h, "real_id": h}
                    added += 1

            self.save_chats()
            self.after(0, self.refresh_chats_ui)

            # Resolve names via TG in background
            if self.is_connected:
                async def _resolve_all():
                    for h in handles:
                        try:
                            entity = await self.client.get_entity(h)
                            from telethon import utils as tgu
                            self.chats[h]["display"] = tgu.get_display_name(entity) or h
                            self.chats[h]["real_id"] = str(entity.id)
                        except Exception: pass
                    self.save_chats()
                    self.after(0, self.refresh_chats_ui)
                asyncio.run_coroutine_threadsafe(_resolve_all(), self.loop)

            status_lbl.configure(
                text=f"✓ Добавлено {added} новых  (пропущено дублей: {len(handles)-added})",
                text_color=CLR_GREEN)
            btn_import.configure(state="normal", text="✓ ИМПОРТ")

        btn_import = ctk.CTkButton(
            win, text="➕  ИМПОРТ", height=44, width=460,
            fg_color=CLR_ACCENT, hover_color=CLR_ACCENT2,
            font=ctk.CTkFont(size=13, weight="bold"),
            corner_radius=12, command=_do_import)
        btn_import.pack(padx=22)

        ctk.CTkButton(win, text="Закрыть", height=28, width=100,
                       fg_color="transparent", text_color=CLR_MUTED,
                       hover_color=CLR_CARD, corner_radius=8,
                       command=win.destroy).pack(pady=(8,0))

    # ─────────────────────────────────────────────────────
    #  CHAT ANALYZER  (scan chats, auto-mark packs)
    # ─────────────────────────────────────────────────────
    def open_chat_analyzer(self):
        """Scan selected chats and auto-mark packs as sent if files match."""
        win = ctk.CTkToplevel(self)
        win.title("🔍  Анализ чатов → паки")
        win.geometry("700x620")
        win.configure(fg_color=CLR_BG)
        win.lift()

        ctk.CTkLabel(win, text="🔍  АНАЛИЗ ЧАТОВ — ПАКИ",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=CLR_CYAN).pack(pady=(18,2), padx=20, anchor="w")
        ctk.CTkLabel(
            win,
            text="Приложение сканирует историю выбранных чатов и сравнивает\n"
                 "названия файлов с файлами в паках. Если совпадает ≥ порога — пак считается отправленным.",
            font=ctk.CTkFont(size=11), text_color=CLR_MUTED, justify="left").pack(
            padx=20, anchor="w")

        # Settings row
        cfg_row = ctk.CTkFrame(win, fg_color=CLR_CARD, corner_radius=10, height=52)
        cfg_row.pack(fill="x", padx=20, pady=10); cfg_row.pack_propagate(False)

        ctk.CTkLabel(cfg_row, text="Порог совпадений:",
                     font=ctk.CTkFont(size=12), text_color=CLR_TEXT).pack(
            side="left", padx=14, pady=10)

        threshold_var = ctk.IntVar(value=50)
        threshold_spin = ctk.CTkSlider(cfg_row, from_=10, to=100, width=180,
                                        variable=threshold_var,
                                        fg_color=CLR_BORDER, progress_color=CLR_ACCENT,
                                        button_color=CLR_ACCENT2)
        threshold_spin.pack(side="left", padx=8, pady=10)
        thr_lbl = ctk.CTkLabel(cfg_row, text="50%",
                                font=ctk.CTkFont(size=12, weight="bold"),
                                text_color=CLR_CYAN)
        thr_lbl.pack(side="left", padx=4)
        def _upd_thr(v):
            thr_lbl.configure(text=f"{int(float(v))}%")
        threshold_spin.configure(command=_upd_thr)

        ctk.CTkLabel(cfg_row, text="Лимит сообщений:",
                     font=ctk.CTkFont(size=12), text_color=CLR_TEXT).pack(
            side="left", padx=(20,8))
        limit_entry = ctk.CTkEntry(cfg_row, width=70, height=32,
                                    fg_color=CLR_PANEL, border_color=CLR_BORDER,
                                    text_color=CLR_TEXT, font=ctk.CTkFont(size=12))
        limit_entry.insert(0, "1000")
        limit_entry.pack(side="left", padx=(0,14))

        # Chat checkboxes
        ctk.CTkLabel(win, text="Выбери чаты для анализа:",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=CLR_TEXT).pack(padx=20, anchor="w", pady=(0,4))

        chat_scroll = ctk.CTkScrollableFrame(win, fg_color=CLR_PANEL,
                                               corner_radius=10, height=200)
        chat_scroll.pack(fill="x", padx=20, pady=(0,8))

        chat_vars = {}
        if not self.chats:
            ctk.CTkLabel(chat_scroll, text="Нет добавленных чатов",
                         text_color=CLR_MUTED).pack(pady=16)
        else:
            sel_all_var = ctk.BooleanVar(value=True)
            def _toggle_all():
                v = sel_all_var.get()
                for cv in chat_vars.values(): cv.set(v)
            ctk.CTkCheckBox(chat_scroll, text="Выбрать все", variable=sel_all_var,
                             fg_color=CLR_ACCENT, checkmark_color="white",
                             font=ctk.CTkFont(size=11, weight="bold"),
                             command=_toggle_all).pack(anchor="w", padx=8, pady=(6,2))
            for raw, data in self.chats.items():
                cv = ctk.BooleanVar(value=True)
                chat_vars[raw] = cv
                ctk.CTkCheckBox(chat_scroll, text=data['display'],
                                 variable=cv, fg_color=CLR_ACCENT,
                                 checkmark_color="white",
                                 font=ctk.CTkFont(size=11)).pack(
                    anchor="w", padx=18, pady=2)

        # Log area
        log_scroll = ctk.CTkScrollableFrame(win, fg_color=CLR_PANEL,
                                             corner_radius=10, height=140)
        log_scroll.pack(fill="x", padx=20, pady=(0,8))
        log_labels = []

        def _log(msg, clr=CLR_TEXT):
            lbl = ctk.CTkLabel(log_scroll, text=msg, font=ctk.CTkFont(size=11),
                                text_color=clr, anchor="w", justify="left")
            lbl.pack(anchor="w", padx=6, pady=1)
            log_labels.append(lbl)
            # auto-scroll
            try: log_scroll._parent_canvas.yview_moveto(1.0)
            except: pass

        # Progress
        prog = ctk.CTkProgressBar(win, width=660, fg_color=CLR_CARD,
                                   progress_color=CLR_ACCENT)
        prog.pack(padx=20, pady=(0,6)); prog.set(0)

        status_lbl = ctk.CTkLabel(win, text="Нажми АНАЛИЗИРОВАТЬ",
                                   font=ctk.CTkFont(size=11), text_color=CLR_MUTED)
        status_lbl.pack(pady=(0,6))

        btn_run = [None]

        def _run_analysis():
            selected_chats = [r for r, v in chat_vars.items() if v.get()]
            if not selected_chats:
                status_lbl.configure(text="Нет выбранных чатов", text_color=CLR_WARN)
                return
            if not self.is_connected:
                status_lbl.configure(text="Telegram не подключён — сначала авторизуйся",
                                      text_color=CLR_WARN)
                return
            if not self.packs:
                status_lbl.configure(text="Нет паков", text_color=CLR_WARN)
                return
            try:
                limit = int(limit_entry.get().strip())
            except ValueError:
                limit = 1000
            threshold = threshold_var.get() / 100.0

            btn_run[0].configure(state="disabled", text="Анализ…")
            for lbl in log_labels: lbl.destroy()
            log_labels.clear()
            prog.set(0)
            status_lbl.configure(text="Сканирование…", text_color=CLR_YELLOW)

            asyncio.run_coroutine_threadsafe(
                self._analyze_chats_task(selected_chats, limit, threshold,
                                          _log, prog, status_lbl, btn_run[0]),
                self.loop)

        btn = ctk.CTkButton(
            win, text="🔍  АНАЛИЗИРОВАТЬ", height=44,
            fg_color=CLR_ACCENT, hover_color=CLR_ACCENT2,
            font=ctk.CTkFont(size=13, weight="bold"),
            corner_radius=12, command=_run_analysis)
        btn.pack(padx=20, pady=(0,14))
        btn_run[0] = btn

    async def _analyze_chats_task(self, selected_chats, limit, threshold,
                                    log_cb, prog_widget, status_lbl, btn):
        total_chats   = len(selected_chats)
        total_marked  = 0
        total_already = 0

        for ci, raw in enumerate(selected_chats, start=1):
            display = self.chats[raw]['display']
            self.after(0, lambda d=display, ci=ci, t=total_chats:
                log_cb(f"[{ci}/{t}] 🔎 Сканируем {d}…", CLR_CYAN))
            self.after(0, lambda ci=ci, t=total_chats:
                prog_widget.set(ci / t * 0.5))

            try:
                entity  = await self.client.get_entity(raw)
                chat_id = str(entity.id)

                # Collect filenames from chat history
                chat_names = set()
                async for msg in self.client.iter_messages(entity, limit=limit):
                    if msg.media and hasattr(msg.media, 'document'):
                        doc = msg.media.document
                        if "audio" in doc.mime_type:
                            fname = next(
                                (a.file_name for a in doc.attributes
                                 if isinstance(a, DocumentAttributeFilename)),
                                "")
                            if fname: chat_names.add(fname.lower())

                # Update tracked_files cache
                if chat_names:
                    existing = {f['name'].lower() for f in self.tracked_files.get(chat_id, [])}
                    new_entries = self.tracked_files.get(chat_id, [])
                    for n in chat_names:
                        if n not in existing:
                            new_entries.append({"name": n, "date": "auto", "size": 0})
                    self.tracked_files[chat_id] = new_entries
                    self.save_tracked()

                self.after(0, lambda d=display, n=len(chat_names):
                    log_cb(f"   → {n} аудио-файлов найдено в чате", CLR_MUTED))

                # Compare each pack
                for pid, pack in self.packs.items():
                    pack_files_lower = {f.lower() for f in pack.get("files", [])}
                    if not pack_files_lower: continue
                    overlap   = len(pack_files_lower & chat_names)
                    ratio     = overlap / len(pack_files_lower)
                    pname     = pack['name']

                    if ratio >= threshold:
                        if not self.is_pack_sent(pid, raw):
                            self.mark_pack_sent(pid, raw)
                            total_marked += 1
                            self.after(0, lambda pn=pname, o=overlap,
                                       t=len(pack_files_lower), d=display:
                                log_cb(f"   ✅ «{pn}» → отмечен ({o}/{t} файлов)", CLR_GREEN))
                        else:
                            total_already += 1
                            self.after(0, lambda pn=pname:
                                log_cb(f"   ✓  «{pn}» уже отмечен", CLR_MUTED))
                    else:
                        self.after(0, lambda pn=pname, o=overlap,
                                   t=len(pack_files_lower), r=int(ratio*100):
                            log_cb(f"   —  «{pn}» не отправлен ({o}/{t} = {r}%)", CLR_MUTED))

            except Exception as e:
                self.after(0, lambda err=str(e):
                    log_cb(f"   ⚠ Ошибка: {err}", CLR_WARN))

        self.after(0, prog_widget.set(1.0))
        self.after(0, lambda: status_lbl.configure(
            text=f"✅ Готово! Новых отметок: {total_marked}  (уже было: {total_already})",
            text_color=CLR_GREEN))
        self.after(0, lambda: btn.configure(state="normal", text="🔍  АНАЛИЗИРОВАТЬ"))
        self.after(0, self.refresh_chats_ui)


# ─────────────────────────────────────────────────────
if __name__ == "__main__":
    app = MP3TrackerApp()
    app.refresh_chats_ui()
    app.mainloop()
