"""Hey Jev's window on Windows: status on top, sidebar tabs for stats, the dictionary, apps, history, settings and keys."""
import json
import os
import queue
import re
import sys
import threading
import time
import tkinter as tk
import webbrowser
from collections import Counter
from pathlib import Path
from tkinter import messagebox, ttk
from typing import NamedTuple

import bubble
import dictation
import hermes_memory
import history
import messaging
import opencode
import secrets_store
import settings
import tasks as tasking
import winplatform as win
from hermes_memory import skills

get_secret = secrets_store.get_secret  # read in a dozen places below
TITLE = "Hey Jev"
HERE = os.path.dirname(os.path.abspath(__file__))
ICON = os.path.join(HERE, "assets", "icon.ico")
W, H, SIDEBAR = 940, 640, 210
HINTS = {"ptt": "Hold right Alt to talk", "wake": "Say \u201cHey Jev\u201d, \u201cHello Jev\u201d or just \u201cJev\u201d, "
                                                 "then what you want. Right after she answers, just keep talking. "
                                                 "Holding right Alt works too."}
ENGINES = {"parakeet": "Parakeet (hears her name best)", "nemotron": "Nemotron (writes as you talk)",
           "whisper": "Whisper small.en (slower)"}
MODE_LABELS = {"ptt": "Hold Right Alt", "wake": "Hey Jev"}  # the two listening modes, in the switch's order
# Each sidebar tab: its key, its name, the method that builds its page once, and the one (if any) that fills the
# page in again every time the tab is opened, so it's never stale
TABS = (("home", "Home", "_make_home_page", "_refresh_home"),
        ("tasks", "Tasks", "_make_tasks_page", "_load_tasks"),
        ("contacts", "Contacts", "_make_contacts_page", "_load_contacts"),
        ("dict", "Dictionary", "_make_dictionary_page", None),
        ("apps", "Apps", "_make_apps_page", None),
        ("hist", "Dictation history", "_make_history_page", "_refresh_history"),
        ("mem", "Memory", "_make_memory_page", "_load_memory"),
        ("priv", "Privacy", "_make_privacy_page", None),
        ("settings", "Settings", "_make_settings_page", "_refresh_settings"),
        ("keys", "Keys", "_make_keys_page", None))
hermes_memory.set_memory_dir(os.path.join(win.APPDATA_DIR, "memories"))  # the same places siri.py keeps them
hermes_memory.set_home(win.APPDATA_DIR)
skills.set_skills_dir(os.path.join(win.APPDATA_DIR, "skills"))
NOTES_DIR = os.path.join(win.APPDATA_DIR, "notes")
# What the window says she's doing, as the popup shows it (see bubble.LOOKS)
PILL = {"Listening": "listening", "Still listening": "window", "Transcribing": "thinking", "Thinking": "thinking",
        "Looking": "looking", "Doing it": "doing", "Speaking": "speaking", "Time's up": "speaking",
        "Dictating": "dictating", "Finishing": "finishing", "Something went wrong": "error", "Phone": "phone"}
# learning your voice: siri says "Read this out loud (3 of 10)" or "Once more (3 of 10)", with the sentence
ENROL = {"Read this out loud": "read", "Once more": "again"}
HOLD = {"error": 3000, "phone": 6000, "note": 2000}  # ms these stay up before fading, nothing replaces them
READY_NEWS = ("That didn't sound like you", "Stopped learning your voice", "Didn't catch")  # why a popup went away
PHONE_BAD = ("Add your", "That code", "Too many", "No code", "Telegram ", "Pairing was busy")  # siri's phone news that's a problem
LOG_FILE = win.log_path("Hey Jev.log")
# What the Home tab counts in that log: one "> heard: ..." line per thing she heard, one "  action: open Notepad"
# line per thing she did
LOG_HEARD = "> heard:"
LOG_ACTION = re.compile(r"  action:\s+(\S+)\s*(.*)")
# "Time saved" is dictation against typing it: people type about 40 words a minute and speak about 150
TYPED_PER_MIN = 40
SPOKEN_PER_MIN = 150
STAT_CARDS = ("Time saved", "Words dictated", "Dictations", "Commands done", "Most opened app", "Questions answered")
ACTION_NAMES = {"open": "Open app", "close": "Close app", "minimise": "Minimise", "website": "Websites",
                "youtube": "YouTube", "google": "Google", "media": "Play and pause", "volume": "Volume",
                "scroll": "Scroll", "keys": "Shortcuts", "type": "Typing", "new_tab": "New tab", "timer": "Timers",
                "dark_mode": "Dark mode", "lock": "Lock", "memory": "Remembered", "screen": "Looked at the screen",
                "skill": "Skills learned", "research": "Research", "note": "Notes", "open_notes": "Notes",
                "task_queued": "Background tasks", "task_control": "Background tasks", "command": "Commands",
                "schedule": "Schedules", "install_run": "Apps installed", "message_send": "Messages sent",
                # names from before the planner, still in older logs
                "app_open": "Open app", "app_quit": "Close app", "app_hide": "Minimise", "app_minimise": "Minimise",
                "app_focus": "Open app", "media_play": "Play and pause", "media_pause": "Play and pause",
                "media_next": "Next track", "media_previous": "Previous track", "timer_set": "Timers",
                "browser_open_site": "Websites", "browser_new_tab": "New tab"}
APPS_FILE = os.path.join(HERE, "apps.json")
MIC_SUB = "Switches straight away. Plugged in a new one? Restart Jev to see it here."
HOW_TO = ("Say \u201cHey Jev\u201d and what you want: \u201cplay Arijit Singh songs\u201d, \u201copen Notepad and "
          "write a poem about rain\u201d, \u201cscroll down\u201d, \u201cwhat\u2019s the weather in Delhi\u201d, "
          "\u201cremind me in 10 minutes to call Mum\u201d. In Hold Right Alt mode, hold right Alt and just say it. "
          "For a few seconds after she answers, keep talking without \u201cHey Jev\u201d. She hears you over YouTube "
          "and music, since Windows takes what the PC plays out of the mic (Settings, Echo cancelling). "
          "\u201cHey Jev, transcribe\u201d starts dictating, and \u201cstop transcribing\u201d pastes it where your cursor is.\n"
          "She remembers: \u201cremember that my website SkillID is skillid.in\u201d, then \u201copen SkillID\u201d. Ask "
          "\u201cwhat did we talk about yesterday?\u201d, or about the PC: \u201chow much space is on my C drive?\u201d, "
          "\u201cis my laptop charging?\u201d. Browser profiles work by name: \u201copen Gmail in my Work profile\u201d.\n"
          "She can see the screen when you ask: \u201cwhat\u2019s on my screen?\u201d, \u201cclick the second video\u201d, "
          "\u201cread this page to me\u201d, \u201csearch for lofi in this box\u201d.\n"
          "Ask her about the world: \u201cwho directed Iron Man 2?\u201d, \u201cwhat\u2019s the latest news?\u201d, "
          "\u201cwill it rain tomorrow?\u201d. \u201cAny new messages?\u201d reads your notifications, and Phone Link "
          "brings in your phone\u2019s. \u201cResearch the best budget phones under 20,000\u201d carries on in the "
          "background, then she tells you and saves a note. Schedule durable work: \u201cevery Monday at 9 check my C "
          "drive\u201d; guarded terminal work: \u201ccheck git status in C:\\path\u201d. The Tasks tab shows, cancels and approves it. "
          "Teach her routines: \u201cwhen I say work mode, open Gmail "
          "in my Work profile and set the volume to 30\u201d, then just say \u201cwork mode\u201d. She learns from your "
          "corrections, and her personality is yours to change in the Memory tab.\n"
          "Closing the window keeps her listening, quit from the sidebar or with Ctrl+Q.")
WHAT_LEAVES = (  # the Privacy tab: what goes where, and why
    ("Stays on your PC", "Everything the mic hears, and all your dictation. Speech is turned into text on this PC to "
     "listen for \u201cHey Jev\u201d, and anything that isn't for her is thrown away, never sent. Simple commands like "
     "\u201copen Notepad\u201d or \u201cpause\u201d are worked out here too, and so are questions about the PC like "
     "\u201chow much space is on my C drive\u201d. The log only keeps phrases that start with \u201chey\u201d, to check "
     "how her name was heard. Her memory, skills, notes, personality (SOUL.md) and your conversations with her are "
     "kept in %APPDATA%\\Hey Jev, see the Memory tab. Your dictionary and apps stay in this folder, logs in "
     "%LOCALAPPDATA%\\Hey Jev."),
    ("Answer model on OpenCode Zen or Kilo  \u00b7  text", "What you ask her, as text: the words after \u201cHey Jev\u201d "
     "and what you say in the few seconds after she answers, with the name of the app in front, what's playing, the "
     "time, her personality, what she remembers about you, her skills, your last half hour with her and the names of "
     "your browser profiles, to work out what to do. With Answer without her name on in Settings, also anything said "
     "near the PC that could be a request, a phrase with a word like open, play or what in it, and up to three things "
     "said in the half minute before it, so she can tell a conversation with someone else. When she looks something "
     "up for it, the answer: how full a drive is, what you said on a day, what a web page says. Once a day, the day "
     "before's conversation, for a short summary and anything worth remembering, and the turns her learning looks "
     "back over, always to space-bunny-free, which keeps nothing and isn't trained on. Other free models may use what "
     "you send to improve the model: opencode.ai/docs/zen lists which on OpenCode, and Kilo says some of its free "
     "ones log what they're sent."),
    ("Messaging  ·  stays on this PC", "Who you can message and their number or username are kept in "
     "%APPDATA%\\Hey Jev\\contacts.json, on this PC. The chat is opened with WhatsApp's or Telegram's own link, so "
     "the message goes to that app and nowhere else, and nothing is sent until you say yes. In an app with no link "
     "of its own she types the name into that app's search instead, which she can't read back, so your yes is "
     "confirming the chat as well; what worked is kept in %APPDATA%\\Hey Jev\\recipes.json. She never reads your "
     "chats, and no screenshot of a chat is taken. The words you dictate reach the answer model only when it had to "
     "work out the request, the same as anything else you say."),
    ("Background tasks  ·  stays on this PC", "Tasks, schedules, command text, working folders, status and command "
     "output are kept in %APPDATA%\\Hey Jev\\tasks.db. Command output is never sent to the answer model or spoken; "
     "the Tasks tab shows it. Jev only says whether it finished."),
    ("Internet  \u00b7  search words, web addresses, roughly where you are", "When you ask about the world, the words "
     "to look up go to Wikipedia, DuckDuckGo\u2019s instant answers and Google News, and she opens pages by their "
     "address, as a browser does. The weather comes from Open-Meteo, for roughly where you are: ipinfo.io works that "
     "out from your internet address. Research does the same in the background. What pages say reaches the answer "
     "model as information, never as instructions, and a page that tries to give her orders is left out."),
    ("Notifications  \u00b7  read on your PC", "She reads Windows\u2019 list of notifications on this PC. Heads-ups and "
     "\u201cwelcome back\u201d only say who it\u2019s from and the app, and nothing is sent for them. What a message "
     "says goes to the answer model only when you ask, as in \u201cany new messages?\u201d. Turn it off in Settings."),
    ("Learning  \u00b7  text", "Now and then, after a correction or a task of a few steps, your last few turns with "
     "her go to the answer model, to pick out a fact to remember, a routine or a word speech-to-text got wrong. What "
     "it finds stays on this PC, in the Memory tab and your Dictionary. Turn it off in Settings."),
    ("Vision  \u00b7  a screenshot", "Only when you ask about the screen, or for something she has to see to do, like "
     "\u201cclick the second video\u201d or \u201cwhat\u2019s on my screen?\u201d: a picture of the screen in front goes to "
     "the answer model, and again after each step she takes there, five at most. Never otherwise. Her popup is left "
     "out of it, and without her name she asks first. Turn it off in Settings."),
    ("YouTube  \u00b7  search words", "When she plays something, what you asked for, to find the top video."),
    ("Fish Audio  \u00b7  text", "The text of her replies, to turn into her voice. Scripted replies are saved after the "
     "first time, so most are never sent again."),
)
API_KEYS = (  # the Keys tab: what it's called, the secret's name, what it's for, where to get one
    ("OpenCode Zen", "OPENCODE_ZEN_API_KEY", "Works out what you asked and answers, on free models only",
     "https://opencode.ai/zen"),
    ("Fish Audio", "FISH_AUDIO_API_KEY", "Her voice, on Fish's free model", "https://fish.audio/"),
    ("Kilo", "KILO_API_KEY", "More free models, like Nemotron 3 Super, free ones only",
     "https://kilo.ai/docs/gateway/authentication"),
    ("Telegram bot", "TELEGRAM_BOT_TOKEN", "Jev on your phone: make a bot with @BotFather, then Settings > Phone > "
     "Pair", "https://core.telegram.org/bots/tutorial#obtain-your-bot-token"),
)

BG, SIDE, HOVER, SELECT, CARD, LINE = "#ffffff", "#f3f3f3", "#e9e9e9", "#e0e0e0", "#f4f4f5", "#e3e3e3"
TEXT, MUTED, ACCENT, ERROR, TEAL = "#1b1b1b", "#5c5c5c", "#0067c0", "#c42b1c", "#0f766e"
# The dot by the status: red while the mic is taking you in, blue while it's being turned into text
DOT_COLOURS = {
    "Starting": "#d97706", "Ready": "#16a34a", "Thinking": "#7c3aed", "Looking": "#0891b2", "Doing it": "#ea580c",
    "Speaking": "#0d9488", "Time's up": "#ca8a04", "Phone": "#229ed9",
    **dict.fromkeys(("Listening", "Still listening", "Dictating", "Something went wrong"), "#dc2626"),
    **dict.fromkeys(("Transcribing", "Finishing"), "#2563eb"),
}


def spoken_key(words):
    """apps.json's key for a name you say: "Claude Code" is claude_code, which is what Jev matches on."""
    return "_".join(re.findall(r"[a-z0-9]+", words.lower()))


def split_list(text):
    return [a.strip() for a in text.split(",") if a.strip()]


def clip(text, most):
    """text cut to at most `most` characters, ending in an ellipsis when something was cut."""
    return text if len(text) <= most else text[:most - 1] + "…"


def countdown(seconds):
    """A timer's time left, as 4:05, or 1:02:03 past the hour. Part of a second still shows as a whole one."""
    hours, rest = divmod(int(seconds + 0.999), 3600)
    return f"{hours}:{rest // 60:02d}:{rest % 60:02d}" if hours else f"{rest // 60}:{rest % 60:02d}"


def time_saved(words):
    """How much quicker saying `words` was than typing them, as "3 h 12 min", "40 min" or "25 sec"."""
    minutes = words * (1 / TYPED_PER_MIN - 1 / SPOKEN_PER_MIN)
    if minutes < 1:
        return f"{minutes * 60:.0f} sec"
    if minutes < 60:
        return f"{minutes:.0f} min"
    hours, rest = divmod(int(minutes), 60)
    return f"{hours} h {rest} min"


def read_dictations():
    """Every finished dictation, oldest first. A line still being written when we read is left out."""
    try:
        lines = Path(dictation.HISTORY).read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    found = []
    for line in lines:
        try:
            found.append(json.loads(line))
        except ValueError:
            pass
    return [d for d in found if isinstance(d, dict)]


class LogTally(NamedTuple):
    heard: int  # things she heard
    answered: int  # questions a model answered
    actions: Counter  # things she did, by kind
    opened: Counter  # apps she opened, by apps.json key


def tally_log(path):
    """Count up Jev's log for the Home tab. No log yet counts as nothing."""
    heard = answered = 0
    actions, opened = Counter(), Counter()
    try:
        log = open(path, encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return LogTally(0, 0, actions, opened)
    with log:
        for line in log:
            done = LOG_ACTION.match(line)
            if done:
                kind, what = done[1], done[2].strip()
                actions[kind] += 1
                if what and kind in ("open", "app_open"):  # app_open is the older name for it
                    opened[what] += 1
            elif line.startswith(LOG_HEARD):
                heard += 1
            elif line.startswith("  llm ") and not line.startswith("  llm failed"):
                answered += 1
    return LogTally(heard, answered, actions, opened)


def read_apps(path):
    """apps.json as editable rows: key (the name you say), app, heard (other spellings), say (how she names it,
    or None) and exe (program names, for quitting and switching)."""
    rows = []
    for key, value in json.loads(Path(path).read_text(encoding="utf-8")).items():
        details = {"app": value} if isinstance(value, str) else value  # a plain string is just the app
        exe = details.get("exe") or []
        rows.append({"key": key, "app": details["app"], "heard": list(details.get("heard_as", [])),
                     "say": details.get("say"), "exe": [exe] if isinstance(exe, str) else list(exe)})
    return rows


def apps_json(rows):
    """The text of apps.json for these rows. Each app gets a line of its own so the file stays easy to edit by hand,
    and an app with nothing but its name is saved as just that name."""
    out = []
    for row in rows:
        exe = row["exe"][0] if len(row["exe"]) == 1 else row["exe"]
        extra = {name: v for name, v in (("say", row["say"]), ("exe", exe), ("heard_as", row["heard"])) if v}
        value = {"app": row["app"], **extra} if extra else row["app"]
        out.append("  %s: %s" % (json.dumps(row["key"]), json.dumps(value, ensure_ascii=False)))
    return "{\n%s\n}\n" % ",\n".join(out)


class HintEntry(ttk.Entry):
    """An entry with grey hint text while it's empty, since Tk entries have no placeholder."""

    def __init__(self, parent, hint, secure=False, **kw):
        super().__init__(parent, **kw)
        self.hint, self.secure, self.showing = hint, secure, False
        self.bind("<FocusIn>", self._hide_hint, add="+")
        self.bind("<FocusOut>", self._show_hint, add="+")
        self._show_hint()

    def _hide_hint(self, _=None):
        if self.showing:
            self.showing = False
            self.delete(0, "end")
            self.configure(style="TEntry", show="\u2022" if self.secure else "")

    def _show_hint(self, _=None):
        if not self.showing and not super().get():
            self.showing = True
            self.configure(style="Hint.TEntry", show="")
            self.insert(0, self.hint)

    def get(self):
        return "" if self.showing else super().get()

    def clear(self):
        self._hide_hint()
        self.delete(0, "end")
        try:
            focused = self.focus_get() is self
        except (KeyError, tk.TclError):
            focused = False
        if not focused:
            self._show_hint()

    def set_hint(self, hint):
        self.hint = hint
        if self.showing:
            self.delete(0, "end")
            self.insert(0, hint)


class AssistantWindow:
    def __init__(self, root):
        self.root = root
        self.controls, self.events = queue.Queue(), queue.Queue()
        self.worker = None  # the assistant's thread, once there are keys to start it with
        self.mode = settings.get("mode") if settings.get("mode") in MODE_LABELS else "ptt"
        self.mic = settings.get("mic") or ""
        self.on_top = bool(settings.get("keep_on_top"))
        self.popup = bool(settings.get("popup"))
        self.s = root.winfo_fpixels("1i") / 96  # Windows display scaling, 1.0 at 100%
        self._setup_root()
        self._setup_styles()
        self.bubble = bubble.Bubble(root)
        self._build_sidebar()
        self._build_main()
        self.pages = {key: getattr(self, make)() for key, _, make, _ in TABS}
        self.tab_refresh = {key: getattr(self, fill) for key, _, _, fill in TABS if fill}
        needs_keys = bool(secrets_store.missing_secrets())  # without them she can't start, so open on Keys
        self.show_tab("keys" if needs_keys else "home")
        self.root.after(50, self._drain)
        self.root.after(500, self._tick)
        self.root.after(150, self.root.focus_force)
        if needs_keys:
            self._set_status("Starting", "Add your API keys to begin")
        else:
            self._launch_assistant()

    def px(self, n):
        return round(n * self.s)

    # ---- The window itself ----
    def _setup_root(self):
        root = self.root
        root.title(TITLE)
        root.configure(bg=BG)
        if os.path.exists(ICON):
            root.iconbitmap(default=ICON)
        w, h = self.px(W), self.px(H)
        x = (root.winfo_screenwidth() - w) // 2
        y = max(0, (root.winfo_screenheight() - h) // 2 - self.px(30))
        root.geometry(f"{w}x{h}+{x}+{y}")
        root.minsize(self.px(820), self.px(560))
        root.attributes("-topmost", self.on_top)
        root.protocol("WM_DELETE_WINDOW", root.iconify)  # closing keeps her listening, the taskbar button brings it back
        root.bind("<Control-q>", lambda e: self.quit())
        root.bind("<Control-m>", lambda e: root.iconify())
        root.bind("<Control-t>", lambda e: self.toggle_on_top())
        for cls in ("TEntry", "TCombobox"):  # Ctrl+T swaps letters in a text box, the window shortcut wins
            root.bind_class(cls, "<Control-t>", lambda e: None)
        root.grid_columnconfigure(1, weight=1)
        root.grid_rowconfigure(0, weight=1)

    def _setup_styles(self):
        self.f_body = ("Segoe UI", 10)
        self.f_small = ("Segoe UI", 9)
        self.f_bold = ("Segoe UI Semibold", 10)
        self.f_h2 = ("Segoe UI Semibold", 11)
        self.f_status = ("Segoe UI Semibold", 13)
        self.f_title = ("Segoe UI Semibold", 17)
        self.f_brand = ("Segoe UI Semibold", 13)
        self.f_value = ("Segoe UI Semibold", 19)
        self.f_mono = ("Consolas", 11)
        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure(".", font=self.f_body)
        style.configure("Treeview", rowheight=self.px(26), font=self.f_body)
        style.configure("Treeview.Heading", font=self.f_bold)
        style.configure("TButton", padding=(self.px(10), self.px(3)))
        style.configure("Hint.TEntry", foreground="#6e6e6e")
        style.configure("TCheckbutton", background=BG)
        style.configure("TCombobox", padding=self.px(2))

    def _label(self, parent, text="", font=None, fg=TEXT, bg=BG, **kw):
        anchor = "nw" if "wraplength" in kw else "w"  # if a long text runs out of room, lose the end, not the start
        return tk.Label(parent, text=text, font=font or self.f_body, fg=fg, bg=bg, anchor=anchor, justify="left", **kw)

    def _link(self, parent, text, url, bg=BG):
        link = tk.Label(parent, text=text, font=("Segoe UI", 9, "underline"), fg=ACCENT, bg=bg, cursor="hand2")
        link.bind("<Button-1>", lambda e: webbrowser.open(url))
        return link

    # ---- Sidebar and header ----
    def _build_sidebar(self):
        side = tk.Frame(self.root, bg=SIDE, width=self.px(SIDEBAR))
        side.grid(row=0, column=0, sticky="ns")
        side.pack_propagate(False)
        self._label(side, "Hey Jev", self.f_brand, bg=SIDE).pack(fill="x", padx=self.px(22), pady=(self.px(22), self.px(14)))
        self.tab_buttons = {}
        for key, title, *_ in TABS:
            b = tk.Button(side, text=title, anchor="w", relief="flat", bd=0, bg=SIDE, fg=TEXT, font=self.f_body,
                          activebackground=SELECT, activeforeground=TEXT, padx=self.px(12), pady=self.px(5),
                          highlightthickness=1, highlightbackground=SIDE, highlightcolor=ACCENT, cursor="hand2",
                          command=lambda k=key: self.show_tab(k))
            b.pack(fill="x", padx=self.px(10), pady=1)
            b.bind("<Enter>", lambda e, k=key: self._hover_tab(k, True))
            b.bind("<Leave>", lambda e, k=key: self._hover_tab(k, False))
            self.tab_buttons[key] = b
        bottom = tk.Frame(side, bg=SIDE)
        bottom.pack(side="bottom", fill="x", padx=self.px(20), pady=(0, self.px(14)))
        self.timer_rows = [self._timer_row(bottom) for _ in range(3)]  # room for three, the soonest at the top
        self.hint = self._label(bottom, HINTS[self.mode], self.f_small, MUTED, SIDE, wraplength=self.px(SIDEBAR - 40))
        self.hint.pack(fill="x", pady=(self.px(8), self.px(6)))
        tk.Button(bottom, text="Quit Hey Jev", relief="flat", bd=0, bg=SIDE, fg=MUTED, font=self.f_small,
                  activebackground=HOVER, cursor="hand2", anchor="w", highlightthickness=1, highlightbackground=SIDE,
                  highlightcolor=ACCENT, command=self.quit).pack(fill="x")

    def _timer_row(self, parent):
        """A timer's line in the sidebar, its name on the left and time left on the right. Packed only while a
        timer is running (see _tick)."""
        row = tk.Frame(parent, bg=SIDE)
        name = self._label(row, "", self.f_small, MUTED, SIDE)
        name.pack(side="left")
        left = tk.Label(row, text="", font=self.f_mono, fg=TEAL, bg=SIDE)
        left.pack(side="right")
        return row, name, left

    def _hover_tab(self, key, inside):
        if key != getattr(self, "current_tab", None):
            self.tab_buttons[key].configure(bg=HOVER if inside else SIDE)

    def _build_main(self):
        main = tk.Frame(self.root, bg=BG)
        main.grid(row=0, column=1, sticky="nsew")
        header = tk.Frame(main, bg=BG)
        header.pack(fill="x", padx=self.px(24), pady=(self.px(16), self.px(12)))
        seg = tk.Frame(header, bg=LINE, padx=1, pady=1)  # the mode switch, a 1px border round two buttons
        seg.pack(side="right", anchor="n")
        self.mode_buttons = {}
        for mode, text in MODE_LABELS.items():
            b = tk.Button(seg, text=text, relief="flat", bd=0, font=self.f_body, padx=self.px(12),
                          pady=self.px(4), cursor="hand2", highlightthickness=0, command=lambda m=mode: self.set_mode(m))
            b.pack(side="left")
            self.mode_buttons[mode] = b
        self._paint_mode()
        status = tk.Frame(header, bg=BG)
        status.pack(side="left", fill="x", expand=True)
        row = tk.Frame(status, bg=BG)
        row.pack(anchor="w")
        self.dot = tk.Label(row, text="\u25cf", font=("Segoe UI", 13), fg=DOT_COLOURS["Starting"], bg=BG)
        self.dot.pack(side="left")
        self.status = self._label(row, "Starting", self.f_status)
        self.status.pack(side="left", padx=(self.px(6), 0))
        self.detail = self._label(status, "Loading speech models\u2026", fg=MUTED)
        self.detail.pack(anchor="w", fill="x")
        tk.Frame(main, bg=LINE, height=1).pack(fill="x")
        self.page_area = tk.Frame(main, bg=BG)
        self.page_area.pack(fill="both", expand=True)
        self.page_area.grid_rowconfigure(0, weight=1)
        self.page_area.grid_columnconfigure(0, weight=1)

    def _paint_mode(self):
        for mode, b in self.mode_buttons.items():
            on = mode == self.mode
            b.configure(bg=ACCENT if on else BG, fg="#ffffff" if on else TEXT,
                        activebackground=ACCENT if on else HOVER, activeforeground="#ffffff" if on else TEXT)

    def _page(self, title, subtitle, scroll=False):
        page = tk.Frame(self.page_area, bg=BG, padx=self.px(24), pady=self.px(18))
        page.grid(row=0, column=0, sticky="nsew")
        if scroll:  # a page taller than the window scrolls, with the mouse wheel too
            outer, canvas = page, tk.Canvas(page, bg=BG, highlightthickness=0, bd=0)
            bar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
            page = tk.Frame(canvas, bg=BG)
            item = canvas.create_window(0, 0, window=page, anchor="nw")
            canvas.configure(yscrollcommand=bar.set)
            canvas.pack(side="left", fill="both", expand=True)

            def fit(event=None):
                if event is not None and event.widget is canvas:
                    canvas.itemconfigure(item, width=event.width)
                canvas.configure(scrollregion=(0, 0, canvas.winfo_width(), page.winfo_reqheight()))
                if page.winfo_reqheight() > canvas.winfo_height() > 1:
                    bar.pack(side="right", fill="y", before=canvas)
                else:
                    bar.pack_forget()
                    canvas.yview_moveto(0)
            page.bind("<Configure>", fit)
            canvas.bind("<Configure>", fit)
            wheel = lambda e: canvas.yview_scroll(int(-e.delta / 120), "units") if bar.winfo_ismapped() else None
            outer.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", wheel))
            outer.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
            page.outer = outer  # what the tabs raise
        self._label(page, title, self.f_title).pack(fill="x")
        self._label(page, subtitle, fg=MUTED, wraplength=self.px(660)).pack(fill="x", pady=(self.px(2), self.px(14)))
        return page

    def _table(self, parent, columns, on_edit=None):
        """A list with a scrollbar. columns maps each column's id to its heading and width. With on_edit, a cell can
        be changed in place, and on_edit(row, column id, new text) is called with the change."""
        frame = tk.Frame(parent, bg=BG)
        tree = ttk.Treeview(frame, columns=list(columns), show="headings", selectmode="browse")
        for column, (heading, width) in columns.items():
            tree.heading(column, text=heading, anchor="w")
            tree.column(column, width=self.px(width), anchor="w", stretch=True)
        bar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=bar.set)
        tree.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        if on_edit:
            tree.bind("<Double-1>", lambda e: self._edit_at(tree, e, on_edit))
            tree.bind("<F2>", lambda e: self._edit_selected(tree, on_edit))  # keyboard way in, F2 like Explorer
        return frame, tree

    def _bottom_bar(self, page, button_text, command):
        bar = tk.Frame(page, bg=BG)
        bar.pack(fill="x", pady=(self.px(10), 0))
        ttk.Button(bar, text=button_text, command=command).pack(side="left")
        message = self._label(bar, "", self.f_small, MUTED)
        message.pack(side="left", padx=self.px(10))
        return message

    # ---- Changing a cell in place ----
    def _edit_at(self, tree, event, on_edit):
        if tree.identify_region(event.x, event.y) != "cell":
            return
        row, col = tree.identify_row(event.y), tree.identify_column(event.x)
        if row:
            self._edit(tree, row, int(col[1:]) - 1, on_edit)

    def _edit_selected(self, tree, on_edit):
        sel = tree.selection()
        if sel:
            self._edit(tree, sel[0], 0, on_edit)

    def _edit(self, tree, row, col, on_edit):
        tree.see(row)
        tree.update_idletasks()
        box = tree.bbox(row, f"#{col + 1}")
        if not box:
            return
        ident = tree["columns"][col]
        entry = ttk.Entry(tree)
        entry.insert(0, tree.set(row, ident))
        entry.select_range(0, "end")
        entry.place(x=box[0], y=box[1], width=box[2], height=box[3])
        entry.focus_set()
        done = [False]

        def finish(save):
            if done[0]:
                return
            done[0] = True
            value = entry.get()
            entry.destroy()
            if save:
                on_edit(int(row), ident, value.strip())

        entry.bind("<Return>", lambda e: finish(True))
        entry.bind("<Escape>", lambda e: finish(False))
        entry.bind("<FocusOut>", lambda e: finish(True))

    # ---- Home tab: the stats cards and how to talk to her ----
    def _make_home_page(self):
        page = self._page("Your Jev stats", "Counted from the day you started with Jev, and brought up to date "
                          "whenever you open this tab.", scroll=True)
        grid = tk.Frame(page, bg=BG)
        grid.pack(fill="x")
        for c in range(3):
            grid.grid_columnconfigure(c, weight=1, uniform="card")
        self.stat_labels = [self._stat_card(grid, place, heading) for place, heading in enumerate(STAT_CARDS)]
        self._label(page, "Most used", self.f_h2).pack(fill="x", pady=(self.px(6), self.px(2)))
        self.top_actions = self._label(page, "", fg=MUTED, wraplength=self.px(660))
        self.top_actions.pack(fill="x")
        self._label(page, "How to use", self.f_h2).pack(fill="x", pady=(self.px(12), self.px(2)))
        self._label(page, HOW_TO, fg=MUTED, wraplength=self.px(660)).pack(fill="x")
        return page

    def _stat_card(self, grid, place, heading):
        """One grey card, three to a row: a big figure, its heading, and a line under it. Returns the two labels
        that change, the figure and that line."""
        row, col = divmod(place, 3)
        card = tk.Frame(grid, bg=CARD, padx=self.px(16), pady=self.px(10))
        card.grid(row=row, column=col, sticky="nsew", padx=(0, self.px(12) if col < 2 else 0), pady=(0, self.px(12)))
        figure = self._label(card, "", self.f_value, bg=CARD)
        figure.pack(fill="x")
        self._label(card, heading, self.f_bold, bg=CARD).pack(fill="x")
        under = self._label(card, "", self.f_small, MUTED, CARD)
        under.pack(fill="x")
        return figure, under

    def _refresh_home(self):
        today = time.strftime("%Y-%m-%d")  # a dictation's time starts with its date, written the same way
        # each dictation as (how many words, whether it was today)
        sized = [(len(str(d.get("text", "")).split()), str(d.get("time", ""))[:10] == today)
                 for d in read_dictations()]
        sizes = [words for words, _ in sized]
        sizes_today = [words for words, is_today in sized if is_today]
        log = tally_log(LOG_FILE)
        # the name she'd say for an app, falling back to how it's listed
        spoken = {row["key"]: row["say"] or row["app"] for row in getattr(self, "apps", [])}
        if log.opened:
            [(top_app, times)] = log.opened.most_common(1)
            top_name, top_note = spoken.get(top_app, top_app.replace("_", " ")), f"opened {times} times"
        else:
            top_name, top_note = "None yet", "Say “Hey Jev, open Spotify”"
        figures = (  # in STAT_CARDS order: the figure, then the line under it
            (time_saved(sum(sizes)), f"compared with typing at {TYPED_PER_MIN} words a minute"),
            (f"{sum(sizes):,}", f"{sum(sizes_today):,} of them today"),
            (f"{len(sizes):,}", f"{len(sizes_today):,} today"),
            (f"{sum(log.actions.values()):,}", f"out of {log.heard:,} things she heard"),
            (clip(top_name, 14), top_note),
            (f"{log.answered:,}", "by free models, $0"),
        )
        for (figure, under), (big, small) in zip(self.stat_labels, figures):
            figure.configure(text=big)
            under.configure(text=small)
        by_name = Counter()  # an action's old and new names add up under the one heading
        for action, times in log.actions.items():
            by_name[ACTION_NAMES.get(action, action.replace("_", " ").capitalize())] += times
        listed = "   ·   ".join(f"{name}  {times}" for name, times in by_name.most_common(6))
        self.top_actions.configure(text=listed or "No commands yet. Say “Hey Jev” and what you’d like "
                                                  "done, and they’ll add up here.")

    # ---- Contacts tab ----
    def _make_contacts_page(self):
        page = self._page("Contacts", "Who Jev can message, and how. She asks once, then remembers. Nothing is ever "
                          "sent until you say yes. Double-click a cell to fix it.")
        frame, self.contacts_table = self._table(page, {"name": ("Name you say", 150),
                                                        "whatsapp": ("WhatsApp number", 170),
                                                        "telegram": ("Telegram username", 170),
                                                        "other": ("Found in other apps as", 190)},
                                                 on_edit=self._contact_edited)
        frame.pack(fill="both", expand=True)
        self.contacts_message = self._bottom_bar(page, "Remove", self.remove_contact)
        self._load_contacts()
        return page

    def _load_contacts(self, message=None):
        self.contacts = sorted(messaging.read_contacts().items())
        self.contacts_table.delete(*self.contacts_table.get_children())
        for row, (key, entry) in enumerate(self.contacts):
            # whatever she learned elsewhere: the name she types into Signal's or Slack's own search
            elsewhere = ", ".join(f"{messaging.say_of(a)}: {h}" for a, h in sorted(entry.items())
                                  if a not in ("name", "whatsapp", "telegram") and h)
            self.contacts_table.insert("", "end", iid=str(row), values=(entry.get("name") or key,
                                       entry.get("whatsapp", ""), entry.get("telegram", ""), elsewhere))
        taught = messaging.learned_apps()
        note = message or f"{len(self.contacts)} saved"
        if taught and not message:
            note += " · also learned to message in " + ", ".join(taught)
        self.contacts_message.configure(text=note, fg=MUTED)

    def _contact_edited(self, row, column, value):
        key, entry = self.contacts[row]

        def rewrite(name):  # a contact is one row per name, so a change means writing the row again
            messaging.forget_contact(key)
            for app, handle in entry.items():
                if app != "name" and handle:
                    messaging.save_contact(name, app, handle)
        if column == "other":
            self._load_contacts("Jev learns those herself, so there's nothing to edit here")
            return
        try:
            if column == "name" and value:
                rewrite(value)
            elif column in ("whatsapp", "telegram"):
                if value:
                    messaging.save_contact(entry.get("name") or key, column, value)
                else:
                    entry.pop(column, None)
                    rewrite(entry.get("name") or key)
            self._load_contacts("Saved")
        except (ValueError, RuntimeError) as exc:
            self._load_contacts(f"Couldn't save: {exc}")

    def remove_contact(self):
        sel = self.contacts_table.selection()
        if not sel:
            self.contacts_message.configure(text="Pick someone in the list first", fg=ERROR)
            return
        key = self.contacts[int(sel[0])][0]
        messaging.forget_contact(key)
        self._load_contacts(f"Removed {key}")

    # ---- Tasks tab ----
    def _make_tasks_page(self):
        page = self._page("Background tasks", "Durable work and reminders. They survive a restart; commands that can "
                          "change things wait for approval.")
        self.task_store = tasking.Store()
        frame, self.tasks_table = self._table(page, {"id": ("ID", 42), "task": ("Task", 245),
                                                     "status": ("Status", 115), "next": ("Next run", 145),
                                                     "result": ("Last result", 220)})
        frame.pack(fill="both", expand=True)
        bar = tk.Frame(page, bg=BG)
        bar.pack(fill="x", pady=(self.px(10), 0))
        ttk.Button(bar, text="Refresh", command=self._load_tasks).pack(side="left")
        ttk.Button(bar, text="Cancel", command=lambda: self._task_action("cancel")).pack(side="left",
                                                                                         padx=(self.px(6), 0))
        ttk.Button(bar, text="Approve", command=lambda: self._task_action("approve")).pack(side="left",
                                                                                           padx=(self.px(6), 0))
        self.tasks_message = self._label(bar, "", self.f_small, MUTED)
        self.tasks_message.pack(side="left", padx=self.px(10))
        return page

    def _load_tasks(self, message=None):
        self.tasks_table.delete(*self.tasks_table.get_children())
        try:
            rows = self.task_store.list(80)
        except Exception as exc:
            self.tasks_message.configure(text=f"Couldn't read tasks: {exc}", fg=ERROR)
            return
        for task in rows:
            due = tasking.describe_due(task["due"]) if task["status"] in ("queued", "waiting_approval") else "—"
            result = task.get("error") or task.get("result") or ""
            result = " ".join(str(result).split())
            self.tasks_table.insert("", "end", iid=str(task["id"]), values=(task["id"], task["description"],
                                    task["status"].replace("_", " "), due, result[:100]))
        self.tasks_message.configure(text=message or f"{len(rows)} task{'s' if len(rows) != 1 else ''}", fg=MUTED)

    def _task_action(self, action):
        selected = self.tasks_table.selection()
        if not selected:
            self.tasks_message.configure(text="Pick a task first", fg=ERROR)
            return
        task_id = int(selected[0])
        ok = self.task_store.cancel(task_id) if action == "cancel" else self.task_store.approve(task_id)
        self._load_tasks(f"Task {task_id} {action + 'led' if action == 'cancel' else 'approved'}" if ok else
                         f"Task {task_id} can't be {action + 'led' if action == 'cancel' else 'approved'}")

    # ---- Dictionary tab: words speech-to-text mishears, and what to put instead ----
    def _make_dictionary_page(self):
        page = self._page("Dictionary", "Words speech-to-text gets wrong. Whatever’s listed as “heard as” "
                                        "is replaced with the word. To change a cell, double-click it or press F2.")
        top = tk.Frame(page, bg=BG)
        top.pack(fill="x", pady=(0, self.px(10)))
        self.new_word = HintEntry(top, "Correct word", width=20)
        self.new_word.pack(side="left")
        self.new_alts = HintEntry(top, "Heard as, comma separated", width=34)
        self.new_alts.pack(side="left", padx=self.px(8))
        self.new_alts.bind("<Return>", lambda e: self.add_word())  # Enter in the last box is the same as the button
        ttk.Button(top, text="Add word", command=self.add_word).pack(side="left")
        self.search = HintEntry(top, "Search", width=16)
        self.search.pack(side="right")
        self.search.bind("<KeyRelease>", lambda e: self._show_words())
        frame, self.words_table = self._table(page, {"word": ("Word", 170), "heard": ("Heard as", 440)},
                                              on_edit=self._word_edited)
        frame.pack(fill="both", expand=True)
        self.dict_message = self._bottom_bar(page, "Remove", self.remove_word)
        self.words = [{"word": word, "heard": list(heard)} for word, heard in dictation.read_vocab().items()]
        self._show_words()
        return page

    def _show_words(self):
        """Fill the list with the words that match the search box: the word or any of its spellings."""
        query = self.search.get().strip().lower()
        self.shown = [w for w in self.words if any(query in s.lower() for s in (w["word"], *w["heard"]))]
        self.words_table.delete(*self.words_table.get_children())
        for row, w in enumerate(self.shown):
            self.words_table.insert("", "end", iid=str(row), values=(w["word"], ", ".join(w["heard"])))

    def _store_words(self, note):
        """Save the dictionary, which dictation picks up at once, and say how that went."""
        colour = MUTED
        try:
            dictation.save_vocab({w["word"]: w["heard"] for w in self.words})
        except Exception as exc:
            note, colour = f"Couldn't save: {exc}", ERROR
        self.dict_message.configure(text=note, fg=colour)
        self._show_words()

    def _word_edited(self, row, column, value):
        changed = self.shown[row]
        if column == "heard":
            changed["heard"] = split_list(value)
        elif value:  # a word can't be emptied, the old one stays
            changed["word"] = value
        self._store_words("Saved, in use from now on")

    def add_word(self):
        word, heard = self.new_word.get().strip(), split_list(self.new_alts.get())
        if not (word and heard):
            self.dict_message.configure(text="Type the word and at least one way it gets misheard", fg=ERROR)
            return
        same = next((w for w in self.words if w["word"].lower() == word.lower()), None)
        if same is None:
            self.words.insert(0, {"word": word, "heard": heard})  # new ones go to the top, where you can see them
        else:  # it's in already: only spellings it doesn't have yet are added
            have = {h.lower() for h in same["heard"]}
            same["heard"].extend(h for h in heard if h.lower() not in have)
        for box in (self.new_word, self.new_alts, self.search):
            box.clear()
        self._store_words(f"Added {word}, in use from now on")
        self.new_word.focus_set()

    def remove_word(self):
        picked = self.words_table.selection()
        if not picked:
            self.dict_message.configure(text="Select a word in the list first", fg=ERROR)
            return
        gone = self.shown[int(picked[0])]
        self.words = [w for w in self.words if w is not gone]
        self._store_words(f"{gone['word']} removed")

    # ---- Apps tab: apps.json, which names open which app ----
    def _make_apps_page(self):
        page = self._page("Apps", "What Jev can open, quit, minimise or switch to. App is how the Start menu lists it, "
                                  "and Program its .exe, needed only when quitting or switching can’t find it. "
                                  "Changes apply after Jev restarts.")
        top = tk.Frame(page, bg=BG)
        top.pack(fill="x", pady=(0, self.px(10)))
        self.app_boxes = tuple(HintEntry(top, hint, width=width) for hint, width in (
            ("Name you say", 16), ("App, as in the Start menu", 24), ("Heard as (optional)", 20)))
        self.new_say, self.new_app, self.new_heard = self.app_boxes
        for place, box in enumerate(self.app_boxes):
            box.pack(side="left", padx=(self.px(8) if place else 0, 0))
        self.new_heard.bind("<Return>", lambda e: self.add_app())
        ttk.Button(top, text="Add app", command=self.add_app).pack(side="left", padx=self.px(8))
        frame, self.apps_table = self._table(page, {"say": ("Name you say", 120), "app": ("App", 160),
                                                    "exe": ("Program", 130), "heard": ("Heard as", 240)},
                                             on_edit=self._app_edited)
        frame.pack(fill="both", expand=True)
        self.apps_message = self._bottom_bar(page, "Remove", self.remove_app)
        self.apps = read_apps(APPS_FILE)
        self._show_apps()
        return page

    def _show_apps(self):
        self.apps_table.delete(*self.apps_table.get_children())
        for row, a in enumerate(self.apps):
            shown = (a["key"].replace("_", " "), a["app"], ", ".join(a["exe"]), ", ".join(a["heard"]))
            self.apps_table.insert("", "end", iid=str(row), values=shown)

    def _store_apps(self, note):
        """Write apps.json and say how that went. Jev reads it when she starts, so changes wait for a restart."""
        colour = MUTED
        try:
            Path(APPS_FILE).write_text(apps_json(self.apps), encoding="utf-8")
        except Exception as exc:
            note, colour = f"Couldn't save: {exc}", ERROR
        self.apps_message.configure(text=note, fg=colour)
        self._show_apps()

    def _app_edited(self, row, column, value):
        changed = self.apps[row]
        if column in ("heard", "exe"):  # both are lists, typed with commas between
            changed[column] = split_list(value)
        elif column == "say":
            changed["key"] = spoken_key(value) or changed["key"]
        elif value:  # the app itself can't be emptied
            changed["app"] = value
        self._store_apps("Saved. Jev uses it once she restarts")

    def add_app(self):
        say, app = self.new_say.get().strip(), self.new_app.get().strip()
        if not (say and app):
            self.apps_message.configure(text="Type the name you say and the app’s name", fg=ERROR)
            return
        key = spoken_key(say)
        if key in {a["key"] for a in self.apps}:
            self.apps_message.configure(text=f"{say} is in the list already", fg=ERROR)
            return
        found = win.find_start_app(app)  # saved under the Start menu's own spelling when there is one
        self.apps.append({"key": key, "app": found[0] if found else app, "heard": split_list(self.new_heard.get()),
                          "say": None, "exe": []})
        for box in self.app_boxes:
            box.clear()
        missing = "" if found else f", but there's no “{app}” in the Start menu"
        self._store_apps(f"Added {say}{missing}. Restart Jev to use it")
        self.new_say.focus_set()

    def remove_app(self):
        picked = self.apps_table.selection()
        if not picked:
            self.apps_message.configure(text="Select an app in the list first", fg=ERROR)
            return
        gone = self.apps.pop(int(picked[0]))
        self._store_apps(f"{gone['key'].replace('_', ' ')} removed. Restart Jev to finish")

    # ---- Dictation history tab ----
    def _make_history_page(self):
        page = self._page("Dictation history", "All you’ve dictated, the latest at the top. It never leaves "
                                               "this PC.")
        frame, self.hist_table = self._table(page, {"time": ("When", 130), "text": ("Text", 520)})
        frame.pack(fill="both", expand=True)
        self.hist_message = self._bottom_bar(page, "Copy", self.copy_history)
        self.hist_table.bind("<Double-1>", lambda e: self.copy_history())
        self.dictated = []  # (when, text), the latest first; filled each time the tab opens
        return page

    def _refresh_history(self):
        self.dictated = [(str(d["time"])[:16], str(d["text"])) for d in reversed(read_dictations())
                         if "time" in d and "text" in d]
        self.hist_table.delete(*self.hist_table.get_children())
        for row, (when, text) in enumerate(self.dictated):
            self.hist_table.insert("", "end", iid=str(row), values=(when, text.replace("\n", " ")))
        empty = "Nothing dictated yet. Say “Hey Jev, transcribe” to begin."
        self.hist_message.configure(text="" if self.dictated else empty, fg=MUTED)

    def copy_history(self):
        """Put the selected dictation on the clipboard, newlines and all (the list shows it on one line)."""
        picked = self.hist_table.selection()
        note, colour = "Select a dictation in the list first", ERROR
        if picked:
            try:
                win.set_clipboard(self.dictated[int(picked[0])][1])
                note, colour = "Copied to the clipboard", MUTED
            except Exception as exc:
                note = str(exc)
        self.hist_message.configure(text=note, fg=colour)

    # ---- Memory tab ----
    def _make_memory_page(self):
        page = self._page("Memory", "What she knows about you, read into everything you ask, her own notes and the "
                                    "skills she\u2019s learned. Say \u201cHey Jev, remember that \u2026\u201d, \u201cforget "
                                    "that \u2026\u201d, or teach her: \u201cwhen I say \u2026, do \u2026\u201d. Kept on this "
                                    "PC, the way Hermes Agent keeps its memory.")
        frame, self.mem_table = self._table(page, {"about": ("About", 110), "text": ("What she remembers", 540)})
        frame.pack(fill="both", expand=True)
        bar = tk.Frame(page, bg=BG)
        bar.pack(fill="x", pady=(self.px(10), 0))
        for i, (text, command) in enumerate((("Forget this", self.forget_memory),
                                             ("Edit personality", self.edit_personality),
                                             ("Open notes", self.open_notes), ("Open the folder", self.open_memory_folder),
                                             ("Clear conversations", self.clear_conversations))):
            ttk.Button(bar, text=text, command=command).pack(side="left", padx=(self.px(6) if i else 0, 0))
        self.mem_message = self._label(page, "", self.f_small, MUTED, wraplength=self.px(660))
        self.mem_message.pack(fill="x", pady=(self.px(6), 0))
        self.memories = []
        return page

    def _load_memory(self, message=None):
        store = hermes_memory.MemoryStore()
        try:
            store.load_from_disk()
            learned = skills.list_skills()
        except Exception as exc:
            self.mem_message.configure(text=f"Couldn't read her memory: {exc}", fg=ERROR)
            return
        self.memories = [("user", e) for e in store.user_entries] + [("memory", e) for e in store.memory_entries] + \
                        [("skill", s) for s in learned]
        self.mem_table.delete(*self.mem_table.get_children())
        about = {"user": "You", "memory": "Her notes", "skill": "Skill"}
        for row, (target, entry) in enumerate(self.memories):
            if target == "skill":  # "work-mode: Their work setup (you say: work mode)"
                says = ", ".join(f"\u201c{t}\u201d" for t in entry["triggers"])
                entry = f"{entry['name']}: {entry['description']}" + (f"  (you say {says})" if says else "")
            self.mem_table.insert("", "end", iid=str(row), values=(about[target], " ".join(entry.split())))
        try:
            turns = history.count()
        except Exception:
            turns = 0
        kept = f"She keeps what you say to her ({turns:,} so far) and can look back through it." if turns else ""
        empty = "" if self.memories else "Nothing yet. Say \u201cHey Jev, remember that \u2026\u201d. "
        self.mem_message.configure(text=message or (empty + kept), fg=MUTED)

    def forget_memory(self):
        sel = self.mem_table.selection()
        if not sel:
            self.mem_message.configure(text="Pick one in the list first", fg=ERROR)
            return
        target, entry = self.memories[int(sel[0])]
        if target == "skill":
            result = skills.delete_skill(entry["dir"], really=True)  # you asked: gone, not archived
        else:
            result = hermes_memory.memory_tool(hermes_memory.MemoryStore(), "remove", target, old_text=entry)
        if result.get("success"):
            self._load_memory("Forgotten")
        else:
            self.mem_message.configure(text=str(result.get("error") or "Couldn't forget that")[:120], fg=ERROR)

    def edit_personality(self):
        """Her SOUL.md in Notepad or whatever opens .md files: how she talks, read fresh for every request."""
        try:
            import siri  # loaded already, she's been listening since the window opened
            siri.soul()  # writes the default the first time
            os.startfile(siri.SOUL_PATH)
            self.mem_message.configure(text="Save the file and she talks that way from the next thing you ask. "
                                            "Delete it to go back to how she was.", fg=MUTED)
        except Exception as exc:
            self.mem_message.configure(text=f"Couldn't open it: {exc}", fg=ERROR)

    def open_notes(self):
        os.makedirs(NOTES_DIR, exist_ok=True)
        os.startfile(NOTES_DIR)

    def open_memory_folder(self):
        os.makedirs(win.APPDATA_DIR, exist_ok=True)
        os.startfile(win.APPDATA_DIR)  # her memory, skills, notes, personality and conversations

    def clear_conversations(self):
        if not messagebox.askyesno(TITLE, "Forget every conversation you've had with her? What she remembers about "
                                          "you stays.", parent=self.root):
            return
        try:
            history.clear()
            self._load_memory("Conversations cleared")
        except Exception as exc:
            self.mem_message.configure(text=str(exc), fg=ERROR)

    # ---- Privacy tab ----
    def _make_privacy_page(self):
        page = self._page("Privacy", "In Hey Jev mode the mic never switches off, but what it hears is worked out on "
                                     "your PC first. Below is all that ever leaves it.", scroll=True)
        for heading, text in WHAT_LEAVES:  # a heading saying where to, then what goes there and when
            self._label(page, heading, self.f_h2).pack(fill="x", pady=(self.px(4), 0))
            self._label(page, text, fg=MUTED, wraplength=self.px(660)).pack(fill="x", pady=(0, self.px(12)))
        return page

    # ---- Settings tab ----
    def _make_settings_page(self):
        page = self._page("Settings", "The microphone Jev listens with, the models she uses, and the window.", scroll=True)
        form = tk.Frame(page, bg=BG)
        form.pack(fill="x")
        form.grid_columnconfigure(0, weight=1)

        def row(r, title, sub):
            self._label(form, title, self.f_h2).grid(row=r * 2, column=0, sticky="w", pady=(self.px(12), 0))
            label = self._label(form, sub, self.f_small, MUTED, wraplength=self.px(310))
            label.grid(row=r * 2 + 1, column=0, sticky="w")
            return label

        self.mic_sub = row(0, "Microphone", MIC_SUB)
        self.mic_menu = ttk.Combobox(form, state="readonly", width=38)
        self.mic_menu.grid(row=0, column=1, rowspan=2, sticky="e")
        self.mic_menu.bind("<<ComboboxSelected>>", lambda e: self.mic_changed())

        row(1, "Answer model", "Free model on OpenCode Zen or Kilo that works out what you asked and answers. "
                               "Refresh lists the free ones that answer here, fastest first.")
        models = tk.Frame(form, bg=BG)
        models.grid(row=2, column=1, rowspan=2, sticky="e")
        self.llm_menu = ttk.Combobox(models, width=29, values=opencode.FALLBACK_FREE)
        self.llm_menu.set(settings.get("llm_model"))
        self.llm_menu.pack(side="left")
        ttk.Button(models, text="Refresh", command=self.refresh_models).pack(side="left", padx=(self.px(6), 0))
        for event in ("<<ComboboxSelected>>", "<Return>", "<FocusOut>"):
            self.llm_menu.bind(event, lambda e: self.model_changed("llm_model", self.llm_menu))

        row(2, "Speech to text", "Turns what you say into text, on this PC. Nemotron shows your words as you talk, "
                                 "but it lost \u201cHey Jev\u201d in a real voice. Takes effect when Hey Jev next starts.")
        self.stt_menu = ttk.Combobox(form, state="readonly", width=38, values=list(ENGINES.values()))
        self.stt_menu.set(ENGINES.get(settings.get("stt_engine"), ENGINES["parakeet"]))
        self.stt_menu.grid(row=4, column=1, rowspan=2, sticky="e")
        self.stt_menu.bind("<<ComboboxSelected>>", lambda e: self.engine_changed())

        row(3, "Hear me over videos", "Windows takes what the PC is playing out of the mic, so she hears you over "
                                      "YouTube and music. Turn it off if she stops hearing you.")
        self.echo_var = tk.BooleanVar(value=bool(settings.get("echo_cancel")))
        ttk.Checkbutton(form, text="Echo cancelling", variable=self.echo_var,
                        command=self.echo_changed).grid(row=6, column=1, rowspan=2, sticky="e")

        row(4, "Keep on top", "Keeps this window above other apps. Ctrl+T switches it too.")
        self.on_top_var = tk.BooleanVar(value=self.on_top)
        ttk.Checkbutton(form, text="Keep window on top", variable=self.on_top_var,
                        command=lambda: self.toggle_on_top(self.on_top_var.get())).grid(row=8, column=1, rowspan=2, sticky="e")

        row(5, "Popup", "A small pill at the bottom of the screen: listening, what she heard, thinking, and what "
                        "she's saying. Dictation and learning your voice always show it.")
        self.popup_var = tk.BooleanVar(value=self.popup)
        ttk.Checkbutton(form, text="Show the popup", variable=self.popup_var,
                        command=self.popup_changed).grid(row=10, column=1, rowspan=2, sticky="e")

        row(6, "Start with Windows", "Opens Hey Jev, minimised, when you sign in.")
        self.startup_var = tk.BooleanVar(value=win.starts_with_windows())
        ttk.Checkbutton(form, text="Start when I sign in", variable=self.startup_var,
                        command=self.startup_changed).grid(row=12, column=1, rowspan=2, sticky="e")

        row(7, "Welcome", "When you sign in or come back to the laptop she says hello, by this name, and asks what "
                          "she can do. Just answer, no \u201cHey Jev\u201d needed.")
        welcome = tk.Frame(form, bg=BG)
        welcome.grid(row=14, column=1, rowspan=2, sticky="e")
        name_box = HintEntry(welcome, "Your name", width=16)
        if settings.get("name"):
            name_box._hide_hint()
            name_box.insert(0, settings.get("name"))
        name_box.pack(side="left")
        for event in ("<Return>", "<FocusOut>"):
            name_box.bind(event, lambda e: self.name_changed(name_box.get()), add="+")
        self.welcome_var = tk.BooleanVar(value=bool(settings.get("welcome")))
        ttk.Checkbutton(welcome, text="Say hello", variable=self.welcome_var,
                        command=lambda: settings.put("welcome", self.welcome_var.get())).pack(side="left",
                                                                                              padx=(self.px(8), 0))

        row(8, "Voice", "Her voice, on Fish Audio\u2019s free model until 30 November, then made on this PC (Jev on "
                        "this PC). Try it plays a line. To use any other Fish voice, paste its link from fish.audio.")
        voice = tk.Frame(form, bg=BG)
        voice.grid(row=16, column=1, rowspan=2, sticky="e")
        self.voice_menu = ttk.Combobox(voice, width=24, values=[self._voice_label(v) for _, v, _ in settings.VOICES])
        self.voice_menu.set(self._voice_label(settings.get("voice")))
        self.voice_menu.pack(side="left")
        ttk.Button(voice, text="Try it", command=self.try_voice).pack(side="left", padx=(self.px(6), 0))
        for event in ("<<ComboboxSelected>>", "<Return>", "<FocusOut>"):
            self.voice_menu.bind(event, lambda e: self.voice_changed())

        row(9, "Vision", "When you ask about the screen, or for something she has to see like \u201cclick the "
                         "second video\u201d, she looks at a screenshot of it and acts on it. Never otherwise.")
        self.vision_var = tk.BooleanVar(value=bool(settings.get("vision")))
        ttk.Checkbutton(form, text="Let her see the screen", variable=self.vision_var,
                        command=lambda: settings.put("vision", self.vision_var.get())).grid(row=18, column=1,
                                                                                            rowspan=2, sticky="e")
        self.switches = {}
        for r, (key, title, sub, text) in enumerate((
                ("no_name", "Without her name", "No \u201cHey Jev\u201d needed: she listens all the time, and the "
                 "answer model works out whether you were talking to her or to someone else. What\u2019s said that "
                 "could be a request goes to it as text.", "Answer without her name"),
                ("call_aware", "During calls", "When WhatsApp, Teams, Zoom, Discord or a browser call has the mic, "
                 "unnamed speech is for the call. Say Jev or Jarvis to talk to her.", "Require her name on calls"),
                ("heads_ups", "Heads-ups", "She speaks up when something needs you: the battery at 20 and 10 "
                 "percent, the C drive nearly full, the PC flat out for a while, the internet going, a new message. "
                 "Quiet from 11 at night to 7 in the morning, except a nearly flat battery.", "Tell me"),
                ("notifications", "Notifications", "She reads the Windows notification list on this PC, for \u201cany "
                 "new messages?\u201d, welcome back and heads-ups. Phone Link brings in your phone\u2019s WhatsApp "
                 "and texts.", "Read my notifications"),
                ("learning", "Learning", "After a correction, or a task that took a few steps, she looks back over it "
                 "and keeps what she learned: a fact, a routine, a word she misheard. It all shows in the Memory tab.",
                 "Learn as she goes")), start=10):
            row(r, title, sub)
            var = self.switches[key] = tk.BooleanVar(value=bool(settings.get(key)))
            ttk.Checkbutton(form, text=text, variable=var, command=lambda k=key, v=var: settings.put(k, v.get())
                            ).grid(row=r * 2, column=1, rowspan=2, sticky="e")
        row(15, "Your voice", "She answers only you, not other people, the TV or a video. Press Learn, or say "
                              "“Hey Jev, learn my voice”, and read her 20 short sentences. She learns your "
                              "voice for a few days first. The recordings stay on this PC.")
        yours = tk.Frame(form, bg=BG)
        yours.grid(row=30, column=1, rowspan=2, sticky="e")
        self.voice_id_var = tk.BooleanVar(value=settings.get("voice_id") != "off")
        ttk.Checkbutton(yours, text="Only answer my voice", variable=self.voice_id_var,
                        command=self.voice_id_changed).pack(side="left")
        ttk.Button(yours, text="Learn", command=self.learn_voice).pack(side="left", padx=(self.px(6), 0))
        row(16, "Phone", "Talk to her from your phone on Telegram. Save your bot's token in Keys, send /start to your "
                         "bot, then type the 8-letter code it replies with here and press Pair. No code? Press Pair "
                         "with the box empty first. Only your account can use it, and anything risky waits for "
                         "your Yes.")
        phone = tk.Frame(form, bg=BG)
        phone.grid(row=32, column=1, rowspan=2, sticky="e")
        self.pair_code = HintEntry(phone, "Code from the bot", width=16)
        self.pair_code.pack(side="left")
        self.pair_code.bind("<Return>", lambda e: self.pair_phone())
        ttk.Button(phone, text="Pair", command=self.pair_phone).pack(side="left", padx=(self.px(6), 0))
        ttk.Button(phone, text="Unpair", command=self.unpair_phone).pack(side="left", padx=(self.px(6), 0))
        # the phone's own line: paired or not, and pairing news, which the shared note below gets written over by
        self.phone_state = self._label(form, "", self.f_small, MUTED, wraplength=self.px(620))
        self.phone_state.grid(row=34, column=0, columnspan=2, sticky="w", pady=(self.px(4), 0))
        self._phone_status()
        self.settings_note = self._label(page, "", self.f_small, MUTED, wraplength=self.px(660))
        self.settings_note.pack(fill="x", pady=(self.px(18), 0))
        self.models_loaded = False
        return page

    def _refresh_settings(self):
        self._refresh_mics()
        if not self.models_loaded:  # asking which models answer takes a while, so only the first time
            self.models_loaded = True
            self.refresh_models()

    def _refresh_mics(self):
        """The mic list as Windows has it now: Automatic first, then each input. Picks the saved one, or Automatic
        when it's been unplugged."""
        self.mic_names = win.input_devices()
        _, auto = win.auto_input()
        choices = [f"Automatic ({auto})"]
        choices += [n + ("  (PC sound only)" if "stereo mix" in n.lower() else "") for n in self.mic_names]
        self.mic_menu.configure(values=choices)
        place = self.mic_names.index(self.mic) + 1 if self.mic in self.mic_names else 0
        self.mic_menu.current(place)
        if place:
            self._mic_note()
            return
        self.mic_sub.configure(text=MIC_SUB, fg=MUTED)
        unplugged = f"{self.mic} can\u2019t be found, so " if self.mic else ""
        self._note(f"{unplugged}Microphone: {auto}. Automatic skips Stereo Mix, which only hears what the PC plays.")

    def mic_changed(self):
        place = self.mic_menu.current()
        self.mic = self.mic_names[place - 1] if place > 0 else ""
        settings.put("mic", self.mic)
        self._tell_assistant("mic", self.mic)
        self._refresh_mics()

    def _mic_note(self):
        self._note(f"Microphone: {self.mic}")
        if "stereo mix" in self.mic.lower():  # it records the speakers, never the person talking
            self.mic_sub.configure(text="Stereo Mix only hears what the PC plays, so she can\u2019t hear you. Pick "
                                        "Automatic or your microphone to talk to her.", fg=ERROR)
        else:
            self.mic_sub.configure(text=MIC_SUB, fg=MUTED)

    def echo_changed(self):
        on = self.echo_var.get()
        settings.put("echo_cancel", on)
        self._tell_assistant("mic", self.mic)  # opens the mic again, the new way
        self._note("Echo cancelling on, she hears you over videos and music" if on else
                   "Echo cancelling off. While a video plays, say \u201cHey Jev\u201d close to the mic, or hold right Alt")

    def pair_phone(self):
        """Pair with the code in the box, or open pairing to get one."""
        typed = self.pair_code.get()
        pasted = re.search(r"code is\s+([A-Za-z0-9]{8})\b", typed, re.I)  # the bot's whole reply, pasted
        code = pasted[1] if pasted else "".join(typed.split())
        if not get_secret("TELEGRAM_BOT_TOKEN"):
            self._phone_status("Add your bot's token in Keys first, then press Pair here.", error=True)
        elif not code and settings.get("telegram_owner"):
            self._phone_status(f"Already paired with {settings.get('telegram_owner_name') or 'your account'}. To "
                               "pair another Telegram account, press Unpair first.")
        elif not code:
            self._tell_assistant("pair phone")
            self._phone_status("Pairing is open for 10 minutes: send /start to your bot on Telegram, then type the "
                               "8-letter code it replies with in the box and press Pair.")
        elif re.fullmatch(r"[A-Za-z0-9]{8}", code):
            self._tell_assistant("pair code", code)
            self.pair_code.clear()
            self._phone_status("Checking the code\u2026")
        else:  # a token or a bot name pasted here would have been taken for a wrong code
            self.pair_code.clear()
            self._phone_status("That isn't a pairing code: it's 8 letters and numbers, from your bot after /start. "
                               "To get one, leave the box empty and press Pair.", error=True)

    def unpair_phone(self):
        self._tell_assistant("unpair phone")
        self._phone_status("Unpairing\u2026")

    def _phone_status(self, news=None, error=False):
        """The Phone row's line: the latest pairing news, else whether it's set up and paired."""
        if news is None:
            if settings.get("telegram_owner"):
                news = f"Paired with {settings.get('telegram_owner_name') or 'your Telegram account'}. Message " \
                       "your bot to talk to her."
            elif not get_secret("TELEGRAM_BOT_TOKEN"):
                news = "Not set up: add your bot's token in Keys."
            else:
                news = "Not paired yet: send /start to your bot, or press Pair with the box empty."
        self.phone_state.configure(text=news, fg=ERROR if error else (TEAL if news.startswith("Paired") else MUTED))

    def learn_voice(self):
        self._tell_assistant("learn voice")
        self._note("Read her each sentence in the popup, one at a time. Say “stop” to stop.")

    def voice_id_changed(self):
        import voiceid
        if not self.voice_id_var.get():
            settings.put("voice_id", "off")
            self._note("She answers everyone again.")
            return
        profile = voiceid.Profile()
        if not profile.ready:  # she needs your voice first; reading the sentences turns it on
            self.voice_id_var.set(False)
            self.learn_voice()
            return
        settings.put("voice_id", "on" if profile.calibrated else "learning")
        self._tell_assistant("voice on")
        self._note("She answers only you." if profile.calibrated else
                   "She's learning your voice for a few days, then she'll answer only you.")

    @staticmethod
    def _voice_label(voice):
        """"Hannah · friendly and clear" for a voice in the list, else the ID itself."""
        voice = voice or settings.VOICES[0][1]
        return next((f"{name} \u00b7 {about}" for name, v, about in settings.VOICES if v == voice), voice)

    @staticmethod
    def _voice_id(text):
        """The voice ID for what's in the voice box: one from the list, or a pasted link or ID. None if neither."""
        t = (text or "").strip()
        for name, v, about in settings.VOICES:
            if t.lower() in (name.lower(), f"{name} \u00b7 {about}".lower()):
                return v
        if t.lower().startswith(("onecore:", "sapi:", "pocket:")):
            return t
        m = re.search(r"[0-9a-f]{32}", t.lower())
        return m[0] if m else None

    def voice_changed(self):
        voice = self._voice_id(self.voice_menu.get())
        if not voice:
            self.voice_menu.set(self._voice_label(settings.get("voice")))
            self._note("That isn\u2019t a recognized voice. Pick one from the list, or paste a voice ID.", error=True)
            return
        self.voice_menu.set(self._voice_label(voice))
        if voice == (settings.get("voice") or settings.VOICES[0][1]):
            return
        settings.put("voice", voice)
        self._note("Voice saved. Her usual replies are made again in it in the background, so for a few minutes some "
                   "may start a moment later.")
        assistant = self._siri()
        if assistant:
            threading.Thread(target=assistant.warm_cache, daemon=True).start()

    def try_voice(self):
        voice = self._voice_id(self.voice_menu.get())
        if not voice:
            self._note("Pick a voice first, or paste a voice\u2019s link from fish.audio.", error=True)
            return
        name = settings.get("name")
        line = f"Hi{' ' + name if name else ''}, this is how I'd sound. Anything you'd like me to do?"
        self._note("Playing a line\u2026")

        def play():
            try:
                import siri
                siri.speak(line, voice=voice)
                self.events.put(("note", "", False))
            except Exception as exc:
                self.events.put(("note", f"Couldn\u2019t play it: {exc}", True))
        threading.Thread(target=play, daemon=True).start()

    def startup_changed(self):
        on = self.startup_var.get()
        try:
            win.set_start_with_windows(on)
            self._note("Hey Jev starts when you sign in" if on else "Hey Jev won't start by itself any more")
        except OSError as exc:
            self.startup_var.set(win.starts_with_windows())
            self._note(f"Couldn't change that: {exc}", error=True)

    def name_changed(self, name):
        name = " ".join(name.split())
        if name == (settings.get("name") or ""):
            return
        settings.put("name", name)
        self._note(f"She'll call you {name}" if name else "She won't use a name")

    def popup_changed(self):
        self.popup = self.popup_var.get()
        settings.put("popup", self.popup)
        if not self.popup:
            self._drop_pill()

    def engine_changed(self):
        engine = list(ENGINES)[self.stt_menu.current()]
        settings.put("stt_engine", engine)
        self._note(f"Saved. Quit Hey Jev and open it again to switch to {ENGINES[engine]}.")

    def model_changed(self, name, box):
        value = box.get().strip()
        if value == (settings.get(name) or ""):
            return
        if value and not opencode.is_free(value):  # free only, a paid model never gets saved
            box.set(settings.get(name))
            self._note(f"{value} isn't free. Hey Jev only uses free models, the ones ending in -free or :free.",
                       error=True)
            return
        settings.put(name, value)
        box.set(settings.get(name))  # an emptied box goes back to the default
        model = settings.get(name)
        key = get_secret("OPENCODE_ZEN_API_KEY")
        if not key:
            self._note(f"Saved, she now thinks with {model}")
            return
        self._note(f"Saved, checking {model} answers\u2026")

        def check():
            ok, result = opencode.check_model(key, model)
            self.events.put(("note", f"{model} answered in {result:.1f}s" if ok else f"{model}: {result}", not ok))
        threading.Thread(target=check, daemon=True).start()

    def refresh_models(self):
        key = get_secret("OPENCODE_ZEN_API_KEY")
        self._note("Checking which free models answer here\u2026" if key else "Getting the list from OpenCode\u2026")

        def fetch():
            try:
                working, free = opencode.working_free_models(key) if key else (None, opencode.free_chat_models())
                self.events.put(("models", working, free))
            except Exception as exc:
                self.events.put(("note", f"Couldn't get the model list: {exc}", True))
        threading.Thread(target=fetch, daemon=True).start()

    def _note(self, text, error=False):
        self.settings_note.configure(text=text, fg=ERROR if error else MUTED)

    def _show_models(self, working, free):
        """working is None without a key to check with, else the free models that answered, fastest first."""
        current = settings.get("llm_model")
        if working is None:
            self.llm_menu.configure(values=free or opencode.FALLBACK_FREE)
            self._note(f"{len(free)} free models on OpenCode. Add your OpenCode key in Keys to check which answer here.")
            return
        self.llm_menu.configure(values=working or free)
        if not working:
            self._note("None of OpenCode's free models answer outside OpenCode right now, so only simple commands like "
                       "\u201copen Notepad\u201d or \u201cpause\u201d work.", error=True)
        elif current not in working and opencode.is_free(current):
            self._note(f"{current} doesn't answer here any more, pick one from the list. Working now: "
                       f"{', '.join(working)}", error=True)
        else:
            self._note(f"{len(working)} of {len(free)} free models answer here, fastest first: {', '.join(working)}. "
                       "The rest are busy, or only run inside OpenCode itself.")

    # ---- Keys tab ----
    def _make_keys_page(self):
        page = self._page("Keys", "Kept in Windows Credential Manager, and never shown again once saved. A key in .env "
                                  "takes priority over these.")
        form = tk.Frame(page, bg=BG)
        form.pack(fill="x")
        form.grid_columnconfigure(0, weight=1)
        self.key_boxes = {row[1]: self._key_row(form, place, *row) for place, row in enumerate(API_KEYS)}
        bar = tk.Frame(page, bg=BG)
        bar.pack(fill="x", pady=(self.px(20), 0))
        ttk.Button(bar, text="Save keys", command=self.save_keys).pack(side="right")
        self.keys_message = self._label(bar, "", self.f_small, ERROR, wraplength=self.px(520))
        self.keys_message.pack(side="left")
        return page

    def _key_row(self, form, place, title, secret, use, url):
        """One key: its name and a link to get one over what it's for on the left, a hidden box on the right."""
        top = place * 2
        head = tk.Frame(form, bg=BG)
        head.grid(row=top, column=0, sticky="w", pady=(self.px(12), 0))
        self._label(head, title, self.f_h2).pack(side="left")
        self._link(head, "Get a key", url).pack(side="left", padx=(self.px(8), 0))
        self._label(form, use, self.f_small, MUTED).grid(row=top + 1, column=0, sticky="w")
        if get_secret(secret):
            hint = "Already saved"
        else:
            hint = "Optional" if secret in secrets_store.OPTIONAL else "Paste key"
        box = HintEntry(form, hint, secure=True, width=40)
        box.grid(row=top, column=1, rowspan=2, sticky="e", pady=(self.px(12), 0))
        box.bind("<Return>", lambda e: self.save_keys())
        return box

    def save_keys(self):
        try:
            typed = {secret: box.get() for secret, box in self.key_boxes.items()}
            typed = {secret: value for secret, value in typed.items() if value}  # an empty box keeps what's saved
            for secret, value in typed.items():
                secrets_store.save_secret(secret, value)
                self.key_boxes[secret].clear()
                self.key_boxes[secret].set_hint("Already saved")
            missing = secrets_store.missing_secrets()
            if missing:
                titles = {row[1]: row[0] for row in API_KEYS}
                self.keys_message.configure(text="Still needed: " + ", ".join(titles.get(m, m) for m in missing),
                                            fg=ERROR)
                return
            import siri  # she may be running already, with the old keys
            siri.reload_keys()
            new_bot = "TELEGRAM_BOT_TOKEN" in typed
            if new_bot:  # the bot starts with it, and pairing opens for 10 minutes
                self._tell_assistant("phone token")
            if new_bot and not settings.get("telegram_owner"):
                done = "Saved. Now send /start to your bot on Telegram and type the code it replies with in " \
                       "Settings > Phone"
            else:
                done = "Saved"
            self.keys_message.configure(text=done, fg=MUTED)
            self._phone_status()
            self._launch_assistant()
        except Exception as exc:
            self.keys_message.configure(text=str(exc), fg=ERROR)

    # ---- Switching tabs ----
    def show_tab(self, key):
        """Bring a tab's page to the front, filled in fresh, and mark its button in the sidebar."""
        fill = self.tab_refresh.get(key)
        if fill:
            fill()
        self.current_tab = key
        getattr(self.pages[key], "outer", self.pages[key]).tkraise()
        for button in self.tab_buttons.values():
            button.configure(bg=SIDE, font=self.f_body)
        self.tab_buttons[key].configure(bg=SELECT, font=self.f_bold)

    # ---- Talking to the assistant ----
    def _launch_assistant(self):
        """Start her on a thread of her own. Only once: saving keys again later calls this too."""
        if self.worker is None:
            self.worker = threading.Thread(target=self._assistant_thread, name="assistant", daemon=True)
            self.worker.start()

    def _assistant_thread(self):
        try:
            import siri  # heavy, with the speech models, so loaded here and not before the window shows
            siri.run_voice_assistant(self.notify, self.controls, self.mode, self.mic)
        except Exception as exc:
            print(f"assistant stopped: {exc}")
            self.events.put(("status", "Something went wrong", str(exc)))

    @staticmethod
    def _siri():
        """The assistant's module once it has loaded, else None. The window is up well before she is."""
        return sys.modules.get("siri")

    def _tell_assistant(self, *message):
        """Queue a message for the assistant: a bare one like "learn voice", or a pair like ("mode", "wake")."""
        self.controls.put(message if len(message) > 1 else message[0])

    def notify(self, state, line=""):
        """How she reports what she's doing. It comes from her threads, so it's only queued here, and _drain shows
        it from Tk's own thread."""
        self.events.put(("status", state, line))

    def _drain(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "status":
                    self._set_status(event[1], event[2])
                elif event[0] == "note":
                    self._note(event[1], error=event[2])
                elif event[0] == "models":
                    self._show_models(*event[1:])
        except queue.Empty:
            pass
        self.root.after(50, self._drain)

    def _drop_pill(self, after_ms=0):
        """Let the popup fade, now or after a while. Showing it again before then keeps it up."""
        self.bubble.hide(after_ms)

    def _set_status(self, state, detail):
        if state == "Heard":  # what she heard you say, on its own line above the popup: nothing else changes
            if self.popup:
                self.bubble.caption(detail)
            return
        self.status.configure(text=state)
        if detail is not None:  # None keeps what's there, like her last reply
            detail = " ".join(str(detail).split())
            self.detail.configure(text=clip(detail, 110))
        enrol = next((look for start, look in ENROL.items() if state.startswith(start)), None)
        self.dot.configure(fg=DOT_COLOURS.get(state, DOT_COLOURS["Listening"] if enrol else TEXT))
        if state == "Phone" and detail:  # next to the code box too, where you're looking
            self._phone_status(detail, error=detail.startswith(PHONE_BAD))
        pill, text = PILL.get(state) or enrol, detail
        if enrol:  # the sentence to read, and how far along: "3/10  Hey Jev, set a timer for five minutes."
            n = re.search(r"(\d+) of (\d+)", state)
            text = f"{n[1]}/{n[2]}  {detail}" if n else detail
        elif state == "Ready" and detail and self.bubble.visible and \
                detail.replace("’", "'").startswith(READY_NEWS):  # why the popup's going, not just a fade
            pill = "note"
        # dictation, your voice's sentences, the phone and why it went away show even with the popup off
        if pill and (self.popup or pill in ("dictating", "finishing", "read", "again", "note", "phone")):
            # "Go ahead" and "Let go of right Alt" are for the window, the popup says Listening
            hint = state == "Listening" and str(detail or "").startswith(("Go ahead", "Let go"))
            self.bubble.show(pill, None if hint else text)
            if pill in HOLD:
                self._drop_pill(HOLD[pill])
        else:
            self._drop_pill(900 if state == "Ready" else 0)

    def _tick(self):
        """Twice a second: the sidebar's timers, each with its time left. Rows with no timer are taken away."""
        snapshot = getattr(self._siri(), "timer_snapshot", None)  # not there until she's finished loading
        timers = snapshot()[:len(self.timer_rows)] if snapshot else []
        for place, (row, name, left) in enumerate(self.timer_rows):
            if place >= len(timers):
                if row.winfo_ismapped():
                    row.pack_forget()
                continue
            label, secs = timers[place]
            name.configure(text=clip(label, 18))
            left.configure(text=countdown(secs))
            if not row.winfo_ismapped():
                row.pack(fill="x", before=self.hint)
        self.root.after(500, self._tick)

    def set_mode(self, mode):
        if mode == self.mode:
            return
        self.mode = mode
        settings.put("mode", mode)
        self.hint.configure(text=HINTS[mode])
        self._paint_mode()
        self._tell_assistant("mode", mode)

    def toggle_on_top(self, value=None):
        self.on_top = (not self.on_top) if value is None else bool(value)
        settings.put("keep_on_top", self.on_top)
        self.root.attributes("-topmost", self.on_top)
        self.on_top_var.set(self.on_top)

    def quit(self):
        self.bubble.close()
        self.root.destroy()


def run_app(args=None):
    """Open Hey Jev's window and run until it's quit, or bring back the copy that's already running.
    args are the command line's, sys.argv unless given."""
    args = sys.argv if args is None else args
    win.prepare_gui()  # before Tk starts, so text is sharp on scaled screens
    if not win.single_instance():
        win.show_existing(TITLE)  # already running with the window closed, bring it back
        return
    root = tk.Tk()
    AssistantWindow(root)
    if "--startup" in args:  # started as you signed in: on the taskbar, she says hello and listens
        root.after(300, root.iconify)
    root.mainloop()
    sys.stdout.flush()
    os._exit(0)  # the mic, keyboard hook and speech threads all stop with the app
