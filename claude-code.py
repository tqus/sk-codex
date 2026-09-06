#!/usr/bin/env python3
"""
sk-coder
"""

import os
import time
import asyncio
import shutil
import json
import subprocess
import sys
import glob
import re
import urllib.parse
import base64
from pathlib import Path
import psutil
from textual.app import App, ComposeResult
from textual.containers import Container, Vertical, Horizontal, VerticalScroll
from textual.widgets import Static, Input, Button, OptionList
from textual.widgets.option_list import Option
from textual.screen import ModalScreen
import aiohttp

# Optional: clipboard copy for code blocks. pip install pyperclip
try:
    import pyperclip
    HAS_PYPERCLIP = True
except ImportError:
    HAS_PYPERCLIP = False

# Optional: inline terminal image rendering. pip install "textual-image[textual]" pillow
try:
    from textual_image.widget import Image as TermImage
    HAS_TERM_IMAGE = True
except ImportError:
    HAS_TERM_IMAGE = False

MASTER_COMMANDS = [
    # -- Core --
    ("/menu", "Open model selector dashboard"),
    ("/skills", "List and execute built-in utility skills"),
    ("/login", "Create or manage a one-time session account"),
    ("/effort", "Set reasoning/thinking effort level (low, med, high)"),
    ("/context", "Toggle including past chat history in AI context (default: off)"),
    ("/new", "Start a fresh topic (ignores prior messages for the next reply)"),
    ("/clear", "Clear chat conversation log and memory file"),
    ("/save", "Manually save current session history to disk"),
    ("/help", "Display available commands and manual"),
    ("/about", "Display SK-Coder engine version details"),
    # -- System --
    ("/sys", "Display full system metrics summary"),
    ("/cpu", "Check current CPU usage breakdown"),
    ("/ram", "Check RAM and memory allocation"),
    ("/temp", "Check hardware and CPU thermal sensors"),
    ("/workspace", "Show absolute working directory path"),
    ("/list", "List files in current working directory"),
    ("/run", "Execute current script or project file"),
    ("/lint", "Run static code analysis and linting"),
    ("/format", "Format source code files automatically"),
    # -- Internet / Web --
    ("/web", "Search the web for a query (also usable by the AI)"),
    # -- GitHub --
    ("/github connect", "Connect a GitHub account with a personal access token"),
    ("/github status", "Show current GitHub connection status"),
    ("/github repos", "List your recent GitHub repositories"),
    ("/github issues", "List open issues: /github issues owner/repo"),
    ("/github issue", "Create an issue: /github issue owner/repo Title | Body"),
    # -- Image generation --
    ("/gemini-key", "Set your Google Gemini API key for image generation"),
    ("/proxy", "Point image generation at your own hosted proxy (no local key needed)"),
    ("/image", "Generate an image from a prompt via Gemini (saves locally)"),
    # -- Model --
    ("/qwen", "Switch directly to Qwen Coder 1.5B (Speed Optimized)"),
    ("/tiny", "Switch directly to Qwen 0.5B (Ultra-fast fallback)"),
    ("/time", "Display current local time and date"),
    ("/shell", "Execute a raw shell command string"),
    ("/exit", "Quit the application cleanly")
]

HISTORY_FILE = Path("sk_coder_history.json")
USER_FILE = Path("sk_coder_user.json")
CONFIG_FILE = Path("sk_coder_config.json")
KNOWLEDGE_FILE = Path("sk_coder_knowledge.json")
DISCLAIMER_FILE = Path("sk_coder_identity.json")
IMAGES_DIR = Path("documents") / "images"

DISCLAIMER_TEXT = (
    "This is SK Cortex — an independent local coding assistant.\n"
    "It is NOT Claude, NOT Claude Code, and is not made by or affiliated with Anthropic.\n"
    "It runs a small local model (via Ollama) plus optional web/GitHub/image tools."
)


def load_identity() -> dict:
    if DISCLAIMER_FILE.exists():
        try:
            return json.loads(DISCLAIMER_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_identity(data: dict) -> None:
    try:
        DISCLAIMER_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def normalize_query(q: str) -> str:
    return re.sub(r"\s+", " ", q.strip().lower())


def load_knowledge() -> dict:
    if KNOWLEDGE_FILE.exists():
        try:
            return json.loads(KNOWLEDGE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_knowledge(kb: dict) -> None:
    try:
        KNOWLEDGE_FILE.write_text(json.dumps(kb, indent=2), encoding="utf-8")
    except Exception:
        pass


def get_cached_knowledge(query: str) -> dict | None:
    kb = load_knowledge()
    return kb.get(normalize_query(query))


def store_knowledge(query: str, info: str) -> None:
    kb = load_knowledge()
    kb[normalize_query(query)] = {
        "query": query,
        "info": info,
        "updated": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    save_knowledge(kb)


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_config(cfg: dict) -> None:
    try:
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except Exception:
        pass


async def github_api_request(token: str, method: str, path: str, json_body: dict | None = None):
    """Call the official GitHub REST API using a personal access token."""
    url = f"https://api.github.com{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "SK-Coder"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.request(
                method, url, headers=headers, json=json_body,
                timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                try:
                    data = await resp.json(content_type=None)
                except Exception:
                    data = {"raw": await resp.text()}
                return resp.status, data
    except Exception as e:
        return 0, {"error": str(e)}


async def gemini_generate_image(api_key: str | None, prompt: str, proxy_url: str | None = None):
    """Generate an image either:
    (a) directly against Google's official Gemini API using a user-supplied key, or
    (b) through a self-hosted proxy server that holds the real key server-side.

    Option (b) is the right approach for a publicly distributed build: the shipped
    app only ever knows a plain URL, never a secret, so there is nothing meaningful
    to extract from the binary. See proxy_server_example.py for a minimal reference
    implementation you control and deploy yourself.
    """
    model = "gemini-3-pro-image" if len(prompt) > 300 else "gemini-3.1-flash-image"

    if proxy_url:
        url = proxy_url.rstrip("/") + "/generate-image"
        payload = {"prompt": prompt, "model": model}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=90)) as resp:
                    try:
                        data = await resp.json(content_type=None)
                    except Exception:
                        data = {"raw": await resp.text()}
                    if resp.status != 200:
                        return None, data, model
                    img_b64 = data.get("image_base64")
                    if img_b64:
                        return base64.b64decode(img_b64), None, model
                    return None, {"error": "Proxy returned no image data", "raw": data}, model
        except Exception as e:
            return None, {"error": str(e)}, model

    if not api_key:
        return None, {"error": "No Gemini API key or proxy_url configured."}, model

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]}
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=90)) as resp:
                try:
                    data = await resp.json(content_type=None)
                except Exception:
                    data = {"raw": await resp.text()}
                if resp.status != 200:
                    return None, data, model
                for cand in data.get("candidates", []):
                    for part in cand.get("content", {}).get("parts", []):
                        inline = part.get("inlineData") or part.get("inline_data")
                        if inline and inline.get("data"):
                            return base64.b64decode(inline["data"]), None, model
                return None, {"error": "No image data returned", "raw": data}, model
    except Exception as e:
        return None, {"error": str(e)}, model


async def web_search(query: str, max_results: int = 5) -> list[dict]:
    """Simple web search using DuckDuckGo's HTML endpoint. No API key required."""
    results = []
    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
    headers = {"User-Agent": "Mozilla/5.0 (SK-Coder)"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    pattern = re.compile(
                        r'<a rel="nofollow" class="result__a" href="(.*?)">(.*?)</a>.*?'
                        r'<a class="result__snippet"[^>]*>(.*?)</a>',
                        re.DOTALL
                    )
                    for match in pattern.finditer(html):
                        raw_url, raw_title, raw_snippet = match.groups()
                        title = re.sub(r"<.*?>", "", raw_title).strip()
                        snippet = re.sub(r"<.*?>", "", raw_snippet).strip()
                        real_url = raw_url
                        if "uddg=" in raw_url:
                            parsed = urllib.parse.parse_qs(urllib.parse.urlparse(raw_url).query)
                            real_url = urllib.parse.unquote(parsed.get("uddg", [raw_url])[0])
                        results.append({"title": title, "url": real_url, "snippet": snippet})
                        if len(results) >= max_results:
                            break
                else:
                    results.append({"title": "Search failed", "url": "", "snippet": f"HTTP {resp.status}"})
    except Exception as e:
        results.append({"title": "Search error", "url": "", "snippet": str(e)})
    return results


class SystemMonitor(Static):
    """Widget displaying real-time system metrics, login state, and effort level."""

    def on_mount(self) -> None:
        self.set_interval(2.0, self.update_metrics)
        self.update_metrics()

    def get_temperature(self) -> str:
        try:
            if hasattr(psutil, "sensors_temperatures"):
                temps = psutil.sensors_temperatures()
                if temps:
                    for key in ["coretemp", "cpu_thermal", "acpitz", "k10temp"]:
                        if key in temps and len(temps[key]) > 0:
                            return f"{temps[key][0].current:.1f}°C"
                    for entries in temps.values():
                        if entries:
                            return f"{entries[0].current:.1f}°C"
        except Exception:
            pass
        return "N/A"

    def update_metrics(self) -> None:
        mem = psutil.virtual_memory()
        cpu = psutil.cpu_percent()
        temp = self.get_temperature()

        ram_used_gb = mem.used / (1024 ** 3)
        ram_total_gb = mem.total / (1024 ** 3)

        app_obj = getattr(self, "app", None)
        user_display = "[#e57053]Not logged in[/] [dim]· Run /login[/dim]"
        effort_display = "[dim]● high · /effort[/dim]"

        if app_obj:
            if getattr(app_obj, "logged_in_user", None):
                user_display = f"[green]{app_obj.logged_in_user}[/green] [dim](One-time)[/dim]"
            if getattr(app_obj, "effort_level", None):
                effort_display = f"[dim]● {app_obj.effort_level} · /effort[/dim]"

        content = (
            "[dim]══ SYSTEM STATUS ══[/dim]\n"
            f"[dim]CPU Usage:[/dim]  [dim]{cpu:.1f}%[/dim]\n"
            f"[dim]RAM Usage:[/dim]  [dim]{ram_used_gb:.1f} GB / {ram_total_gb:.1f} GB[/dim]\n"
            f"[dim]CPU Temp:[/dim]   [dim]{temp}[/dim]\n"
            "[dim]────────────────────────[/dim]\n"
            f"{user_display}\n"
            f"{effort_display}"
        )
        self.update(content)


class DisclaimerModal(ModalScreen):
    """Mandatory first-run modal: states clearly this is not Claude/Claude Code,
    and asks the person what to call them. Cannot be dismissed without a name."""

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static("[bold #e57053]═══ BEFORE YOU START ═══[/bold #e57053]", classes="modal-title"),
            Static(f"[bold white]{DISCLAIMER_TEXT}[/bold white]"),
            Static(""),
            Static("[dim]What should this app call you?[/dim]"),
            Input(placeholder="Enter your name...", id="identity-input"),
            Button("I understand — continue", id="btn_ack"),
            classes="modal-box"
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_ack":
            name = self.query_one("#identity-input", Input).value.strip()
            if not name:
                name = "Guest"
            self.app.display_name = name
            save_identity({"display_name": name, "acknowledged": True})
            self.app.update_header()
            self.dismiss()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        name = event.value.strip() or "Guest"
        self.app.display_name = name
        save_identity({"display_name": name, "acknowledged": True})
        self.app.update_header()
        self.dismiss()


class LoginModal(ModalScreen):
    """One-time account creation & login modal."""

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static("[bold #e57053]═══ ONE-TIME ACCOUNT LOGIN ═══[/bold #e57053]", classes="modal-title"),
            Static("[dim]Create or restore a temporary local session account:[/dim]"),
            Input(placeholder="Enter custom username...", id="username-input"),
            Button("Generate Random One-Time Account", id="btn_generate"),
            Button("Save & Login", id="btn_login"),
            Button("Cancel", id="btn_cancel"),
            classes="modal-box"
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        chat_container = self.app.query_one("#chat-container", VerticalScroll)

        if btn_id == "btn_generate":
            import random
            rand_id = f"coder_{random.randint(1000, 9999)}"
            self.app.logged_in_user = rand_id
            self.app.save_user_session()
            self.app.run_worker(chat_container.mount(Static(f"[dim]✓ Generated and logged in as one-time account: {rand_id}[/dim]", classes="system-msg")))
            self.app.query_one("#sys-monitor", SystemMonitor).update_metrics()
            self.dismiss()
        elif btn_id == "btn_login":
            inp = self.query_one("#username-input", Input).value.strip()
            if inp:
                self.app.logged_in_user = inp
                self.app.save_user_session()
                self.app.run_worker(chat_container.mount(Static(f"[dim]✓ Logged in successfully as: {inp}[/dim]", classes="system-msg")))
                self.app.query_one("#sys-monitor", SystemMonitor).update_metrics()
            self.dismiss()
        else:
            self.dismiss()


class ModelSelectorModal(ModalScreen):
    """Model Selector modal optimized for speed on 8GB RAM."""

    def __init__(self, current_model: str):
        super().__init__()
        self.current_model = current_model

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static("[bold #e57053]═══ MODEL SELECTOR ═══[/bold #e57053]", classes="modal-title"),
            Static(f"[dim]Provider: Ollama (localhost:11434)[/]"),
            Static(f"[dim]Current Model: {self.current_model}[/]"),
            Static("[dim]Select fast profile (optimized low num_predict & num_ctx):[/dim]"),
            OptionList(
                Option("qwen2:0.5b (Ultra-lightweight base model)", id="qwen2:0.5b"),
                Option("qwen2.5-coder:1.5b (Coding profile)", id="qwen2.5-coder:1.5b"),
                id="model-list"
            ),
            Button("Close Dashboard", id="btn_close"),
            classes="modal-box"
        )

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        model_id = event.option.id
        if model_id:
            self.app.model = model_id
            chat_container = self.app.query_one("#chat-container", VerticalScroll)
            self.app.run_worker(chat_container.mount(Static(f"[dim]│ Active model switched to: {model_id}[/dim]", classes="system-msg")))
            self.app.update_header()
            self.dismiss()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss()


class SkillsModal(ModalScreen):
    """Modal for selecting and running built-in developer skills instantly."""

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static("[bold #e57053]═══ SK-CODER SKILLS TOOLKIT ═══[/bold #e57053]", classes="modal-title"),
            Static("[dim]Select a utility skill to run instantly against your workspace:[/dim]"),
            OptionList(
                Option("Scan & List all Python/Code files in workspace", id="skill_scan"),
                Option("Run local security pattern check (secrets/keys scanner)", id="skill_security"),
                Option("Generate project README.md automatically", id="skill_readme"),
                Option("Count lines of code & workspace statistics", id="skill_stats"),
                Option("Purge temporary cache / Python bytecode files", id="skill_clean"),
                id="skills-list"
            ),
            Button("Close Toolkit", id="btn_close_skills"),
            classes="modal-box"
        )

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        skill_id = event.option.id
        chat_container = self.app.query_one("#chat-container", VerticalScroll)
        self.dismiss()
        self.app.run_worker(self.app.run_skill(skill_id, chat_container))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss()


class SKCodeApp(App):
    """SK Cortex: an independent Textual TUI coding assistant with persistent history and built-in skills.
    Visually inspired by terminal coding-assistant UIs, but clearly its own product — not Claude or Claude Code."""

    CSS = """
    Screen { 
        background: #202028; 
        color: #d9d9d9; 
        overflow-x: hidden;
    }

    #header-panel { 
        background: transparent; 
        border: none; 
        padding: 1 2; 
        height: auto; 
    }

    .ascii-logo { 
        color: #d9d9d9; 
    }

    #main-container { 
        height: 1fr; 
        width: 100%; 
        overflow-x: hidden;
    }

    #chat-container { 
        background: transparent; 
        border: none; 
        padding: 0 2; 
        width: 1fr; 
        height: 100%; 
        overflow-y: auto;
        overflow-x: hidden;
    }

    .user-msg {
        color: #d9d9d9;
        margin-top: 1;
    }

    .thinking-msg {
        color: #88aaff;
        background: #252535;
        border-left: solid #5588ff;
        padding: 0 1;
        margin-top: 1;
    }

    .assistant-msg {
        color: #d9d9d9;
        margin-top: 1;
    }

    .user-msg, .thinking-msg, .assistant-msg, .system-msg, .stats-msg, .code-block {
        transition: opacity 200ms;
    }

    .stats-msg {
        color: #888;
        margin-bottom: 1;
    }

    .system-msg {
        color: #888;
        margin-top: 1;
        margin-bottom: 1;
    }

    .code-block {
        color: #d9d9d9;
        background: #1a1a22;
        border: solid #3a3a48;
        padding: 1;
        margin-top: 1;
    }

    .copy-btn {
        width: auto;
        margin-bottom: 1;
        background: #2b2b36;
        color: #88cc88;
        border: solid #444;
    }

    .copy-btn:hover {
        border: solid #88cc88;
    }

    #sys-monitor { 
        width: 35; 
        height: 100%; 
        background: transparent; 
        border-left: none; 
        padding: 1 2; 
    }

    #command-autocomplete {
        dock: bottom;
        background: #2b2b36;
        border: solid #444;
        height: 12;
        margin: 0 2;
        visibility: hidden;
    }

    #status-bar { 
        background: transparent; 
        color: #888; 
        padding: 0 2; 
        height: 1; 
        border-top: none; 
        visibility: hidden; 
    }

    #input-container { 
        dock: bottom; 
        background: transparent; 
        border-top: none; 
        height: 3; 
        padding: 0 2; 
    }

    #prompt-symbol { 
        color: #5c5c5c; 
        text-style: bold; 
        width: 2; 
        content-align: left middle; 
    }

    #user-input { 
        background: transparent; 
        border: none; 
        color: #d9d9d9; 
    }

    #user-input:focus {
        border: none;
    }

    ModalScreen { 
        align: center middle; 
        background: rgba(0, 0, 0, 0.8); 
    }

    .modal-box { 
        background: #24242d; 
        border: solid #444; 
        padding: 2 4; 
        width: 65; 
        height: auto; 
        align: center middle; 
    }

    .modal-title { 
        color: #e57053; 
        margin-bottom: 1; 
        text-align: center; 
    }

    OptionList { 
        background: #1e1e26; 
        border: solid #333; 
        height: 8; 
        margin-top: 1; 
        margin-bottom: 1; 
    }

    Button { 
        width: 100%; 
        margin-top: 1; 
        background: #2b2b36; 
        color: #f0f0f0; 
        border: solid #444; 
    }

    Button:hover { 
        border: solid #e57053; 
        color: #e57053; 
    }
    """

    def __init__(self):
        super().__init__()
        self.provider = "ollama"
        self.model = "qwen2:0.5b"
        self.effort_level = "high"
        self.logged_in_user = self.load_user_session()
        self.conversation_history = self.load_history()

        identity = load_identity()
        self.display_name = identity.get("display_name")
        self.disclaimer_acknowledged = identity.get("acknowledged", False)

        cfg = load_config()
        self.github_token = cfg.get("github_token")
        self.gemini_api_key = cfg.get("gemini_api_key")
        self.proxy_url = cfg.get("proxy_url")
        self.use_context = cfg.get("use_context", False)
        self.skip_context_once = False
        self.last_image_date = cfg.get("last_image_date")
        self.images_used_today = cfg.get("images_used_today", 0)
        self.code_snippets: dict[str, str] = {}

    def persist_config(self) -> None:
        save_config({
            "github_token": self.github_token,
            "gemini_api_key": self.gemini_api_key,
            "proxy_url": getattr(self, "proxy_url", None),
            "use_context": self.use_context,
            "last_image_date": getattr(self, "last_image_date", None),
            "images_used_today": getattr(self, "images_used_today", 0)
        })

    def check_image_quota(self) -> bool:
        """Enforce a 1-image-per-day limit."""
        today = time.strftime("%Y-%m-%d")
        if self.last_image_date != today:
            self.last_image_date = today
            self.images_used_today = 0
        return self.images_used_today < 1

    def record_image_used(self) -> None:
        self.images_used_today = getattr(self, "images_used_today", 0) + 1
        self.persist_config()

    async def deliver_image(self, img_bytes: bytes, chat_container: VerticalScroll) -> str:
        """Save the image and, if possible, render it inline in the chat instead of just a file path."""
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        fname = f"image_{time.strftime('%Y%m%d_%H%M%S')}.png"
        fpath = IMAGES_DIR / fname
        fpath.write_bytes(img_bytes)
        if HAS_TERM_IMAGE:
            try:
                await chat_container.mount(TermImage(str(fpath), classes="assistant-msg"))
                return f"[dim]✓ Image generated (saved to {fpath})[/dim]"
            except Exception:
                pass
        return f"[dim]✓ Image saved to {fpath} — install `textual-image` + `pillow` to view images inline in chat.[/dim]"


    def load_history(self) -> list:
        if HISTORY_FILE.exists():
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def save_history(self) -> None:
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.conversation_history, f, indent=2)
        except Exception:
            pass

    def load_user_session(self) -> str | None:
        if USER_FILE.exists():
            try:
                with open(USER_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("username")
            except Exception:
                pass
        return None

    def save_user_session(self) -> None:
        try:
            with open(USER_FILE, "w", encoding="utf-8") as f:
                json.dump({"username": self.logged_in_user}, f, indent=2)
        except Exception:
            pass

    def compose(self) -> ComposeResult:
        header_text = self._build_header_text()
        yield Vertical(Static(header_text, classes="ascii-logo"), id="header-panel")
        yield Horizontal(
            VerticalScroll(id="chat-container"),
            SystemMonitor(id="sys-monitor"),
            id="main-container"
        )
        yield OptionList(id="command-autocomplete")
        yield Static("", id="status-bar")
        yield Horizontal(
            Static(">", id="prompt-symbol"),
            Input(placeholder="Type a message or command (type '/' to filter commands)...", id="user-input"),
            id="input-container"
        )

    def _build_header_text(self) -> str:
        cwd = os.getcwd()
        name = getattr(self, "display_name", None)
        user_str = f" · Hi, {name}" if name else ""
        return (
            f"[#4db8ff]└─$[/] [#4db8ff]sk-cortex[/]\n"
            f"[#e57053]  █████████[ [/] [bold white]SK Cortex[/bold white] [dim]v1.0{user_str}[/dim]\n"
            f"[#e57053]████ ███ ████[/] [dim]model: {self.model} · local via Ollama[/dim]\n"
            f"[#e57053] ██████████ [/] [dim]{cwd}[/dim]\n"
            f"[#e57053]  █ █  █ █ [/]\n"
            f"[bold #ff8866]Claude Code — independent project by SK Cortex[/bold #ff8866]\n"
        )

    def update_header(self) -> None:
        self.query_one(".ascii-logo", Static).update(self._build_header_text())

    async def mount_animated(self, chat_container: VerticalScroll, widget, duration: float = 0.22):
        """Mount a widget and fade it in smoothly instead of popping in instantly."""
        widget.styles.opacity = 0.0
        await chat_container.mount(widget)
        widget.styles.animate("opacity", value=1.0, duration=duration, easing="out_cubic")
        return widget

    async def on_mount(self) -> None:
        chat_container = self.query_one("#chat-container", VerticalScroll)

        if not self.disclaimer_acknowledged:
            self.push_screen(DisclaimerModal())

        if self.conversation_history:
            await chat_container.mount(Static(f"[dim]│ Restored {len(self.conversation_history)} past messages from {HISTORY_FILE.name}:[/dim]", classes="system-msg"))
            for msg in self.conversation_history:
                role = msg.get("role")
                content = msg.get("content", "")
                if role == "user":
                    await chat_container.mount(Static(f"[dim]>[/dim] {content}", classes="user-msg"))
                elif role == "assistant":
                    await chat_container.mount(Static(content, classes="assistant-msg"))
            await chat_container.mount(Static("", classes="system-msg"))

        self.query_one("#user-input", Input).focus()
        self.run_worker(self.warmup_model(chat_container))

    async def warmup_model(self, chat_container: VerticalScroll) -> None:
        """Pre-load the model into Ollama's memory so the first real message doesn't
        pay the cold-start cost. Also keeps it loaded for 30 min between requests."""
        status_widget = Static("[dim]⚡ Warming up model for faster first response...[/dim]", classes="system-msg")
        await chat_container.mount(status_widget)
        endpoint = "http://localhost:11434/api/chat"
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
            "keep_alive": "30m",
            "options": {"num_predict": 1}
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(endpoint, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    if resp.status == 200:
                        status_widget.update("[dim]✓ Model warmed up — ready for fast responses.[/dim]")
                    else:
                        status_widget.update("[dim]Model warm-up skipped (Ollama not ready yet).[/dim]")
        except Exception:
            status_widget.update("[dim]Model warm-up skipped (couldn't reach Ollama at localhost:11434).[/dim]")

    def on_input_changed(self, event: Input.Changed) -> None:
        val = event.value
        autocomplete = self.query_one("#command-autocomplete", OptionList)

        if val.startswith("/"):
            query = val[1:].lower()
            filtered = [item for item in MASTER_COMMANDS if query in item[0].lower()]

            autocomplete.clear_options()
            if filtered:
                for cmd, desc in filtered:
                    autocomplete.add_option(Option(f"{cmd} - {desc}", id=cmd[1:]))
                autocomplete.styles.visibility = "visible"
            else:
                autocomplete.styles.visibility = "hidden"
        else:
            autocomplete.styles.visibility = "hidden"

    def on_key(self, event) -> None:
        autocomplete = self.query_one("#command-autocomplete", OptionList)
        if autocomplete.styles.visibility == "visible":
            if event.key == "down":
                autocomplete.focus()
                event.prevent_default()
            elif event.key == "up":
                autocomplete.focus()
                event.prevent_default()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        opt_id = event.option.id
        autocomplete = self.query_one("#command-autocomplete", OptionList)
        autocomplete.styles.visibility = "hidden"
        user_input = self.query_one("#user-input", Input)
        user_input.value = ""
        user_input.focus()

        chat_container = self.query_one("#chat-container", VerticalScroll)
        if opt_id:
            self.run_worker(self.execute_command(opt_id, chat_container))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        user_text = event.value.strip()
        event.input.value = ""
        event.input.focus()

        autocomplete = self.query_one("#command-autocomplete", OptionList)
        autocomplete.styles.visibility = "hidden"

        if not user_text:
            return

        chat_container = self.query_one("#chat-container", VerticalScroll)

        if user_text.startswith("/"):
            parts = user_text.split()
            cmd_key = parts[0][1:].lower().replace("-", "_")
            cmd_args = parts[1:] if len(parts) > 1 else []
            self.run_worker(self.execute_command(cmd_key, chat_container, raw_text=user_text, args=cmd_args))
        else:
            self.run_worker(self.stream_response(user_text, chat_container))

    async def execute_command(self, cmd_id: str, chat_container: VerticalScroll, raw_text: str = "", args: list = None) -> None:
        args = args or []
        if not raw_text:
            await self.mount_animated(chat_container, Static(f"[dim]>[/dim] /{cmd_id}", classes="user-msg"))
        else:
            await self.mount_animated(chat_container, Static(f"[dim]>[/dim] {raw_text}", classes="user-msg"))

        if cmd_id == "login":
            self.push_screen(LoginModal())
        elif cmd_id == "effort":
            if args and args[0].lower() in ["low", "med", "medium", "high"]:
                lvl = args[0].lower()
                if lvl == "medium":
                    lvl = "med"
                self.effort_level = lvl
                await chat_container.mount(Static(f"[dim]✓ Reasoning effort level set to: {self.effort_level}[/dim]", classes="system-msg"))
                self.query_one("#sys-monitor", SystemMonitor).update_metrics()
            else:
                levels = ["low", "med", "high"]
                curr_idx = levels.index(self.effort_level) if self.effort_level in levels else 2
                self.effort_level = levels[(curr_idx + 1) % len(levels)]
                await chat_container.mount(Static(f"[dim]✓ Effort level toggled to: {self.effort_level} (Usage: /effort [low|med|high])[/dim]", classes="system-msg"))
                self.query_one("#sys-monitor", SystemMonitor).update_metrics()
        elif cmd_id == "menu":
            self.push_screen(ModelSelectorModal(self.model))
        elif cmd_id == "skills":
            self.push_screen(SkillsModal())
        elif cmd_id == "web":
            query = " ".join(args).strip()
            if not query:
                await chat_container.mount(Static("[dim]Usage: /web <search query>[/dim]", classes="system-msg"))
            else:
                await self.search_with_cache(query, chat_container)
        elif cmd_id == "context":
            self.use_context = not self.use_context
            self.persist_config()
            state = "ON (recent chat history is sent to the AI)" if self.use_context else "OFF (each message is answered fresh, ignoring old chat)"
            await chat_container.mount(Static(f"[dim]✓ Context memory: {state}[/dim]", classes="system-msg"))
        elif cmd_id == "new":
            self.skip_context_once = True
            await chat_container.mount(Static("[dim]✓ Next message will be answered fresh, ignoring prior chat.[/dim]", classes="system-msg"))
        elif cmd_id == "github":
            await self.handle_github_command(args, raw_text, chat_container)
        elif cmd_id == "gemini_key":
            key = args[0].strip() if args else ""
            if not key:
                await chat_container.mount(Static("[dim]Usage: /gemini-key <your_api_key>  (get one free at aistudio.google.com)[/dim]", classes="system-msg"))
            else:
                self.gemini_api_key = key
                self.persist_config()
                await chat_container.mount(Static("[dim]✓ Gemini API key saved. Try /image <prompt> to generate an image.[/dim]", classes="system-msg"))
        elif cmd_id == "proxy":
            url = args[0].strip() if args else ""
            if not url:
                current = getattr(self, "proxy_url", None)
                msg = (f"[dim]Current proxy: {current}[/dim]" if current
                       else "[dim]No proxy configured. Usage: /proxy <https://your-server.com>[/dim]")
                await chat_container.mount(Static(msg, classes="system-msg"))
            else:
                self.proxy_url = url
                self.persist_config()
                await chat_container.mount(Static(
                    f"[dim]✓ Image requests will now route through {url} instead of a local API key.[/dim]",
                    classes="system-msg"
                ))
        elif cmd_id == "image":
            prompt = " ".join(args).strip()
            if not prompt:
                await chat_container.mount(Static("[dim]Usage: /image <description of the image>[/dim]", classes="system-msg"))
            elif not self.gemini_api_key and not getattr(self, "proxy_url", None):
                await chat_container.mount(Static("[dim]No Gemini API key or proxy configured. Run /gemini-key <key>, or /proxy <url> if this build ships with a hosted proxy.[/dim]", classes="system-msg"))
            elif not self.check_image_quota():
                await chat_container.mount(Static("[dim]Daily image limit reached (1/day). Try again tomorrow.[/dim]", classes="system-msg"))
            else:
                await chat_container.mount(Static(f"[dim]Generating image: {prompt}[/dim]", classes="system-msg"))
                chat_container.scroll_end()
                img_bytes, err, used_model = await gemini_generate_image(self.gemini_api_key, prompt, proxy_url=getattr(self, "proxy_url", None))
                if img_bytes:
                    self.record_image_used()
                    msg = await self.deliver_image(img_bytes, chat_container)
                    await chat_container.mount(Static(f"{msg}\n[dim](model: {used_model})[/dim]", classes="system-msg"))
                else:
                    await chat_container.mount(Static(f"[dim]Image generation failed ({used_model}): {err}[/dim]", classes="system-msg"))
        elif cmd_id in ["clear", "reset"]:
            await chat_container.remove_children()
            self.conversation_history.clear()
            if HISTORY_FILE.exists():
                try:
                    HISTORY_FILE.unlink()
                except Exception:
                    pass
            await chat_container.mount(Static("[dim]Conversation memory and saved history file cleared successfully.[/dim]", classes="system-msg"))
        elif cmd_id == "save":
            self.save_history()
            await chat_container.mount(Static(f"[dim]Session successfully saved to {HISTORY_FILE.name}[/dim]", classes="system-msg"))
        elif cmd_id == "help":
            await chat_container.mount(Static(
                "[dim]SK-Coder Command Manual: '/skills' for built-in tools, '/login' for accounts, "
                "'/effort' for reasoning level, '/web <query>' for internet search, "
                "'/github connect <token>' to automate GitHub tasks, "
                "'/gemini-key <key>' + '/image <prompt>' for AI image generation, "
                "'/context' to toggle chat memory (off by default so unrelated questions get fresh answers).[/dim]",
                classes="system-msg"
            ))
        elif cmd_id in ["about", "version"]:
            await chat_container.mount(Static("[dim]SK Cortex v1.0 — independent local coding assistant, not affiliated with Anthropic/Claude. Low-latency 8GB-optimized local models + optional web search.[/dim]", classes="system-msg"))
        elif cmd_id in ["sys", "cpu", "ram", "temp"]:
            mem = psutil.virtual_memory()
            cpu = psutil.cpu_percent()
            await chat_container.mount(Static(f"[dim]System Status -> CPU: {cpu}% | RAM: {mem.percent}% used | User: {self.logged_in_user or 'None'}[/dim]", classes="system-msg"))
        elif cmd_id in ["tiny", "qwen2"]:
            self.model = "qwen2:0.5b"
            self.update_header()
            await chat_container.mount(Static("[dim]Switched model to qwen2:0.5b (Ultra-fast)[/dim]", classes="system-msg"))
        elif cmd_id in ["qwen", "coder"]:
            self.model = "qwen2.5-coder:1.5b"
            self.update_header()
            await chat_container.mount(Static("[dim]Switched model to qwen2.5-coder:1.5b[/dim]", classes="system-msg"))
        elif cmd_id == "workspace" or cmd_id == "list":
            await chat_container.mount(Static(f"[dim]│ Current Directory: {os.getcwd()}[/dim]", classes="system-msg"))
            for f in os.listdir("."):
                await chat_container.mount(Static(f"[dim] - {f}[/dim]", classes="system-msg"))
        elif cmd_id == "time":
            await chat_container.mount(Static(f"[dim]│ Current Time: {time.strftime('%Y-%m-%d %H:%M:%S')}[/dim]", classes="system-msg"))
        elif cmd_id == "exit":
            self.save_history()
            self.exit()
        else:
            await chat_container.mount(Static(f"[dim]Executed command routine: /{cmd_id}[/dim]", classes="system-msg"))

        chat_container.scroll_end()

    async def search_with_cache(self, query: str, chat_container: VerticalScroll) -> str:
        """Check the saved-knowledge file first, then always also search the live web,
        show both, and update the file with the fresh results. Returns combined text
        for the AI to use in its follow-up answer."""
        cached = get_cached_knowledge(query)
        if cached:
            await chat_container.mount(Static(
                f"[dim]📚 Checking my saved notes first (from {cached['updated']})...[/dim]\n[dim]{cached['info']}[/dim]",
                classes="system-msg"
            ))
            chat_container.scroll_end()

        await chat_container.mount(Static(f"[dim]🔎 Also checking the internet for: {query}[/dim]", classes="system-msg"))
        chat_container.scroll_end()
        results = await web_search(query)
        if results:
            results_text = "\n".join(f"- {r['title']}: {r['snippet']} ({r['url']})" for r in results)
            for r in results:
                await chat_container.mount(Static(
                    f"  [dim]• {r['title']}\n    {r['snippet']}\n    {r['url']}[/dim]",
                    classes="system-msg"
                ))
        else:
            results_text = "No results found."
            await chat_container.mount(Static("[dim]No results found.[/dim]", classes="system-msg"))

        store_knowledge(query, results_text)
        return results_text

    async def handle_github_command(self, args: list, raw_text: str, chat_container: VerticalScroll) -> None:
        if not args:
            await chat_container.mount(Static(
                "[dim]Usage: /github connect <token> | status | repos | issues owner/repo | issue owner/repo Title | Body[/dim]",
                classes="system-msg"
            ))
            return

        sub = args[0].lower()
        rest = args[1:]

        if sub == "connect":
            token = rest[0].strip() if rest else ""
            if not token:
                await chat_container.mount(Static("[dim]Usage: /github connect <personal_access_token>[/dim]", classes="system-msg"))
                return
            status, data = await github_api_request(token, "GET", "/user")
            if status == 200:
                self.github_token = token
                self.persist_config()
                await chat_container.mount(Static(f"[dim]✓ Connected to GitHub as {data.get('login')}[/dim]", classes="system-msg"))
            else:
                await chat_container.mount(Static(f"[dim]GitHub connection failed (HTTP {status}): {data}[/dim]", classes="system-msg"))

        elif sub == "status":
            if not self.github_token:
                await chat_container.mount(Static("[dim]Not connected. Run /github connect <token>.[/dim]", classes="system-msg"))
            else:
                status, data = await github_api_request(self.github_token, "GET", "/user")
                if status == 200:
                    await chat_container.mount(Static(f"[dim]✓ Connected as {data.get('login')} ({data.get('name') or 'no name set'})[/dim]", classes="system-msg"))
                else:
                    await chat_container.mount(Static(f"[dim]Token saved but invalid/expired (HTTP {status}).[/dim]", classes="system-msg"))

        elif sub == "repos":
            if not self.github_token:
                await chat_container.mount(Static("[dim]Not connected. Run /github connect <token> first.[/dim]", classes="system-msg"))
                return
            status, data = await github_api_request(self.github_token, "GET", "/user/repos?per_page=10&sort=updated")
            if status == 200 and isinstance(data, list):
                await chat_container.mount(Static("[dim]│ Recent repositories:[/dim]", classes="system-msg"))
                for repo in data:
                    await chat_container.mount(Static(f"  [dim]• {repo.get('full_name')} {'(private)' if repo.get('private') else ''}[/dim]", classes="system-msg"))
            else:
                await chat_container.mount(Static(f"[dim]Failed to list repos (HTTP {status}): {data}[/dim]", classes="system-msg"))

        elif sub == "issues":
            repo = rest[0].strip() if rest else ""
            if not repo:
                await chat_container.mount(Static("[dim]Usage: /github issues owner/repo[/dim]", classes="system-msg"))
                return
            if not self.github_token:
                await chat_container.mount(Static("[dim]Not connected. Run /github connect <token> first.[/dim]", classes="system-msg"))
                return
            status, data = await github_api_request(self.github_token, "GET", f"/repos/{repo}/issues?state=open")
            if status == 200 and isinstance(data, list):
                if not data:
                    await chat_container.mount(Static(f"[dim]No open issues in {repo}.[/dim]", classes="system-msg"))
                for issue in data[:10]:
                    await chat_container.mount(Static(f"  [dim]• #{issue.get('number')} {issue.get('title')}[/dim]", classes="system-msg"))
            else:
                await chat_container.mount(Static(f"[dim]Failed to list issues (HTTP {status}): {data}[/dim]", classes="system-msg"))

        elif sub == "issue":
            if not self.github_token:
                await chat_container.mount(Static("[dim]Not connected. Run /github connect <token> first.[/dim]", classes="system-msg"))
                return
            if "|" not in raw_text or len(rest) < 2:
                await chat_container.mount(Static("[dim]Usage: /github issue owner/repo Title text | Body text[/dim]", classes="system-msg"))
                return
            before, body_part = raw_text.split("|", 1)
            before_parts = before.split()
            repo = before_parts[2] if len(before_parts) > 2 else ""
            title = " ".join(before_parts[3:]).strip()
            body = body_part.strip()
            if not repo or not title:
                await chat_container.mount(Static("[dim]Usage: /github issue owner/repo Title text | Body text[/dim]", classes="system-msg"))
                return
            status, data = await github_api_request(self.github_token, "POST", f"/repos/{repo}/issues", {"title": title, "body": body})
            if status in (200, 201):
                await chat_container.mount(Static(f"[dim]✓ Created issue: {data.get('html_url')}[/dim]", classes="system-msg"))
            else:
                await chat_container.mount(Static(f"[dim]Failed to create issue (HTTP {status}): {data}[/dim]", classes="system-msg"))

        else:
            await chat_container.mount(Static(
                "[dim]Unknown GitHub subcommand. Use: connect, status, repos, issues, issue[/dim]",
                classes="system-msg"
            ))

    async def run_skill(self, skill_id: str, chat_container: VerticalScroll) -> None:
        await chat_container.mount(Static(f"[dim]══ Executing Skill: {skill_id} ══[/dim]", classes="system-msg"))

        if skill_id == "skill_scan":
            files = [os.path.join(dp, f) for dp, dn, filenames in os.walk(".") for f in filenames if not ".git" in dp and not "__pycache__" in dp]
            await chat_container.mount(Static(f"[dim]│ Found {len(files)} files in workspace:[/dim]", classes="system-msg"))
            for fp in files[:20]:
                await chat_container.mount(Static(f"  [dim]• {fp}[/dim]", classes="system-msg"))
            if len(files) > 20:
                await chat_container.mount(Static(f"  [dim]... and {len(files) - 20} more files.[/dim]", classes="system-msg"))

        elif skill_id == "skill_security":
            patterns = [r"api[_-]?key", r"secret", r"password", r"token", r"bearer"]
            found_issues = 0
            for dp, dn, filenames in os.walk("."):
                if ".git" in dp or "__pycache__" in dp:
                    continue
                for f in filenames:
                    if f.endswith((".py", ".json", ".env", ".md", ".txt")):
                        fpath = os.path.join(dp, f)
                        try:
                            with open(fpath, "r", encoding="utf-8", errors="ignore") as file_obj:
                                content = file_obj.read()
                                for pat in patterns:
                                    if re.search(pat, content, re.IGNORECASE):
                                        await chat_container.mount(Static(f"  [dim]⚠ Potential credential match '{pat}' in {fpath}[/dim]", classes="system-msg"))
                                        found_issues += 1
                        except Exception:
                            pass
            if found_issues == 0:
                await chat_container.mount(Static("[dim]✓ No obvious hardcoded secrets or keys detected in workspace text files.[/dim]", classes="system-msg"))
            else:
                await chat_container.mount(Static(f"[dim]Completed security scan. Found {found_issues} potential matches to review.[/dim]", classes="system-msg"))

        elif skill_id == "skill_readme":
            readme_path = Path("README.md")
            if readme_path.exists():
                await chat_container.mount(Static("[dim]README.md already exists in working directory.[/dim]", classes="system-msg"))
            else:
                try:
                    with open(readme_path, "w", encoding="utf-8") as r_file:
                        r_file.write("# Project Workspace\n\nManaged via SK-Coder TUI.\n")
                    await chat_container.mount(Static("[dim]✓ Generated default README.md successfully.[/dim]", classes="system-msg"))
                except Exception as e:
                    await chat_container.mount(Static(f"[dim]Failed to create README.md: {e}[/dim]", classes="system-msg"))

        elif skill_id == "skill_stats":
            total_lines = 0
            file_count = 0
            for dp, dn, filenames in os.walk("."):
                if ".git" in dp or "__pycache__" in dp:
                    continue
                for f in filenames:
                    if f.endswith((".py", ".js", ".ts", ".json", ".md", ".html", ".css")):
                        file_count += 1
                        try:
                            with open(os.path.join(dp, f), "r", encoding="utf-8", errors="ignore") as fo:
                                total_lines += sum(1 for _ in fo)
                        except Exception:
                            pass
            await chat_container.mount(Static(f"[dim]│ Workspace Statistics:[/dim]", classes="system-msg"))
            await chat_container.mount(Static(f"  [dim]• Scanned Source Files: {file_count}[/dim]", classes="system-msg"))
            await chat_container.mount(Static(f"  [dim]• Total Lines of Code: {total_lines}[/dim]", classes="system-msg"))

        elif skill_id == "skill_clean":
            removed_count = 0
            for dp, dn, filenames in os.walk("."):
                if "__pycache__" in dp:
                    for f in filenames:
                        try:
                            os.remove(os.path.join(dp, f))
                            removed_count += 1
                        except Exception:
                            pass
            await chat_container.mount(Static(f"[dim]✓ Cleaned {removed_count} bytecode files from __pycache__ directories.[/dim]", classes="system-msg"))

        await chat_container.mount(Static("", classes="system-msg"))
        chat_container.scroll_end()

    async def auto_save_code_blocks(self, response_text: str, chat_container: VerticalScroll) -> None:
        pattern = r"```([a-zA-Z0-9_-]*)\n(.*?)```"
        matches = re.findall(pattern, response_text, re.DOTALL)
        if not matches:
            return

        docs_dir = Path("documents")
        docs_dir.mkdir(exist_ok=True)

        ext_map = {
            "python": "py", "py": "py",
            "html": "html", "htm": "html",
            "cpp": "cpp", "c++": "cpp", "cc": "cpp", "c": "c",
            "json": "json",
            "javascript": "js", "js": "js",
            "typescript": "ts", "ts": "ts",
            "css": "css",
            "markdown": "md", "md": "md",
            "bash": "sh", "sh": "sh", "shell": "sh"
        }

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        for idx, (lang, code_content) in enumerate(matches, 1):
            lang_clean = lang.lower().strip() if lang else "txt"
            ext = ext_map.get(lang_clean, lang_clean if lang_clean else "txt")
            filename = f"snippet_{timestamp}_{idx}.{ext}"
            filepath = docs_dir / filename
            code_text = code_content.strip()
            try:
                filepath.write_text(code_text, encoding="utf-8")
                await chat_container.mount(Static(
                    f"[dim]✓ Saved [{lang_clean}] to documents/{filename}[/dim]\n"
                    f"[dim]────── copy-paste block ({lang_clean}) ──────[/dim]\n"
                    f"{code_text}",
                    classes="code-block"
                ))
                if HAS_PYPERCLIP:
                    code_id = f"copy_{timestamp}_{idx}"
                    self.code_snippets[code_id] = code_text
                    await chat_container.mount(Button(f"📋 Copy {lang_clean} snippet to clipboard", id=code_id, classes="copy-btn"))
                else:
                    await chat_container.mount(Static("[dim](install `pyperclip` to enable a one-click Copy button)[/dim]", classes="system-msg"))
            except Exception as e:
                await chat_container.mount(Static(f"[dim]Failed to auto-save code block: {e}[/dim]", classes="system-msg"))
        chat_container.scroll_end()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id.startswith("copy_") and HAS_PYPERCLIP:
            code = self.code_snippets.get(btn_id)
            if code:
                try:
                    pyperclip.copy(code)
                    event.button.label = "✓ Copied to clipboard!"
                except Exception:
                    event.button.label = "Copy failed"

    async def _ask_ollama_once(self, payload: dict, assistant_widget: Static, chat_container: VerticalScroll) -> str:
        """Send one non-streaming-style request to Ollama, streaming tokens into assistant_widget."""
        endpoint = "http://localhost:11434/api/chat"
        full = ""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(endpoint, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    if resp.status == 200:
                        async for line in resp.content:
                            if line:
                                try:
                                    chunk_data = json.loads(line.decode("utf-8"))
                                    msg_chunk = chunk_data.get("message", {})
                                    c = msg_chunk.get("content", "")
                                    if c:
                                        full += c
                                        assistant_widget.update(full)
                                        chat_container.scroll_end()
                                except Exception:
                                    pass
                    else:
                        err_text = await resp.text()
                        full = f"Ollama error (HTTP {resp.status}): {err_text}"
                        assistant_widget.update(full)
        except Exception as e:
            full = f"Connection error to Ollama (localhost:11434): {str(e)}"
            assistant_widget.update(full)
        return full

    async def stream_response(self, prompt: str, chat_container: VerticalScroll) -> None:
        status_bar = self.query_one("#status-bar", Static)
        status_bar.styles.visibility = "visible"
        status_bar.update(f"  [dim]{self.model} (effort: {self.effort_level}) generating...[/dim]")

        await self.mount_animated(chat_container, Static(f"[dim]>[/dim] {prompt}", classes="user-msg"))

        num_predict_map = {"low": 96, "med": 192, "high": 384}
        max_tokens = num_predict_map.get(self.effort_level, 192)

        thinking_widget = Static("[dim]Thinking process: analyzing query...[/dim]", classes="thinking-msg")
        assistant_widget = Static("[dim]Generating response...[/dim]", classes="assistant-msg")

        await self.mount_animated(chat_container, thinking_widget)
        await self.mount_animated(chat_container, assistant_widget)
        chat_container.scroll_end()

        self.conversation_history.append({"role": "user", "content": prompt})

        include_history = self.use_context and not self.skip_context_once
        self.skip_context_once = False
        if include_history:
            recent_history = self.conversation_history[-4:]
        else:
            recent_history = [self.conversation_history[-1]]

        endpoint = "http://localhost:11434/api/chat"

        effort_prompts = {
            "low": "Give a direct, concise answer immediately, but first state in one short <think> line what the user wants.",
            "med": "In <think> tags, briefly state what the user wants and what you'll provide, then give a clear answer.",
            "high": "In <think> tags, reason step-by-step: state what the user wants, what info/tools you need, and what you'll provide — then deliver the comprehensive response."
        }

        system_prompt = (
            "You are an ultra-fast coding assistant with optional internet and GitHub access. "
            "Answer the user's latest message directly and on-topic; do not repeat or default back "
            "to earlier unrelated answers. "
            "If a question needs current or real-world information you don't already know "
            "(recent events, live prices, docs you're unsure of, etc.), respond with ONLY the line "
            "'SEARCH: <your query>' and nothing else. "
            "If the user wants a GitHub action performed and a token is connected, respond with ONLY "
            "'GITHUB: <json action>' e.g. GITHUB: {\"action\": \"list_issues\", \"repo\": \"owner/repo\"} "
            "or GITHUB: {\"action\": \"create_issue\", \"repo\": \"owner/repo\", \"title\": \"...\", \"body\": \"...\"}. "
            "If the user wants an image generated, respond with ONLY 'IMAGE: <description>'. "
            "When writing code, always put it in a fenced ```language code block so it can be copied. "
            f"{effort_prompts.get(self.effort_level, '')}"
        )
        if self.logged_in_user:
            system_prompt += f" Current user session: {self.logged_in_user}."

        messages = [{"role": "system", "content": system_prompt}] + recent_history

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "keep_alive": "30m",
            "options": {
                "num_predict": max_tokens,
                "temperature": 0.2 if self.effort_level == "low" else 0.1,
                "top_k": 10,
                "top_p": 0.85,
                "num_ctx": 1024
            }
        }

        full_response = ""
        thinking_text = ""
        is_thinking = False
        has_shown_thinking = False
        start_time = time.time()
        eval_count = 0
        eval_duration = 0

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(endpoint, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    if resp.status == 200:
                        status_bar.styles.visibility = "hidden"

                        async for line in resp.content:
                            if line:
                                try:
                                    chunk_data = json.loads(line.decode("utf-8"))

                                    if chunk_data.get("done", False):
                                        eval_count = chunk_data.get("eval_count", 0)
                                        eval_duration = chunk_data.get("eval_duration", 0)

                                    message_chunk = chunk_data.get("message", {})
                                    chunk = message_chunk.get("content", "")

                                    if chunk:
                                        if "<think>" in chunk:
                                            is_thinking = True
                                            chunk = chunk.replace("<think>", "")
                                        if "</think>" in chunk:
                                            is_thinking = False
                                            parts = chunk.split("</think>")
                                            thinking_text += parts[0]
                                            chunk = parts[1] if len(parts) > 1 else ""

                                        if is_thinking:
                                            thinking_text += chunk
                                            has_shown_thinking = True
                                            thinking_widget.update(f"[dim]🧠 Thinking Process:\n{thinking_text.strip()}[/dim]")
                                        else:
                                            if has_shown_thinking and thinking_text and not thinking_widget.renderable:
                                                pass
                                            full_response += chunk
                                            if not full_response.strip():
                                                assistant_widget.update("[dim]Generating response...[/dim]")
                                            else:
                                                assistant_widget.update(full_response)
                                        chat_container.scroll_end()
                                except Exception:
                                    pass

                        if not has_shown_thinking or not thinking_text.strip():
                            await thinking_widget.remove()
                        else:
                            thinking_widget.update(f"[dim]Thinking Process:\n{thinking_text.strip()}[/dim]")

                        # If the model asked to search the internet, do it, then get a final answer
                        stripped = full_response.strip()
                        if stripped.upper().startswith("SEARCH:"):
                            search_query = stripped.split(":", 1)[1].strip()
                            await chat_container.mount(Static(
                                f"[dim]🧠 The user wants information about: {search_query}. Looking that up now.[/dim]",
                                classes="thinking-msg"
                            ))
                            assistant_widget.update(f"[dim]🔎 Searching for: {search_query}[/dim]")
                            chat_container.scroll_end()

                            results_text = await self.search_with_cache(search_query, chat_container)

                            followup_messages = messages + [
                                {"role": "assistant", "content": full_response},
                                {"role": "user", "content": f"Saved notes + web search results:\n{results_text}\n\nNow answer the original question using these results."}
                            ]
                            followup_payload = dict(payload)
                            followup_payload["messages"] = followup_messages

                            assistant_widget.update("[dim]Generating response...[/dim]")
                            full_response = await self._ask_ollama_once(followup_payload, assistant_widget, chat_container)

                        elif stripped.upper().startswith("GITHUB:"):
                            action_str = stripped.split(":", 1)[1].strip()
                            await chat_container.mount(Static(
                                "[dim]🧠 The user wants a GitHub action performed. Running it now.[/dim]",
                                classes="thinking-msg"
                            ))
                            result_text = "Could not run GitHub action."
                            if not self.github_token:
                                result_text = "No GitHub account connected. Ask the user to run /github connect <token>."
                            else:
                                try:
                                    action = json.loads(action_str)
                                except Exception:
                                    action = None
                                if not action:
                                    result_text = "Invalid GitHub action format."
                                elif action.get("action") == "list_issues" and action.get("repo"):
                                    status, data = await github_api_request(self.github_token, "GET", f"/repos/{action['repo']}/issues?state=open")
                                    if status == 200 and isinstance(data, list):
                                        result_text = "\n".join(f"#{i.get('number')} {i.get('title')}" for i in data[:10]) or "No open issues."
                                    else:
                                        result_text = f"GitHub API error (HTTP {status}): {data}"
                                elif action.get("action") == "create_issue" and action.get("repo") and action.get("title"):
                                    status, data = await github_api_request(
                                        self.github_token, "POST", f"/repos/{action['repo']}/issues",
                                        {"title": action["title"], "body": action.get("body", "")}
                                    )
                                    if status in (200, 201):
                                        result_text = f"Created issue: {data.get('html_url')}"
                                    else:
                                        result_text = f"GitHub API error (HTTP {status}): {data}"
                                else:
                                    result_text = "Unsupported or incomplete GitHub action."

                            await chat_container.mount(Static(f"[dim]│ GitHub result:[/dim]\n[dim]{result_text}[/dim]", classes="system-msg"))
                            chat_container.scroll_end()

                            followup_messages = messages + [
                                {"role": "assistant", "content": full_response},
                                {"role": "user", "content": f"GitHub action result:\n{result_text}\n\nNow reply to the user summarizing this."}
                            ]
                            followup_payload = dict(payload)
                            followup_payload["messages"] = followup_messages
                            assistant_widget.update("[dim]Generating response...[/dim]")
                            full_response = await self._ask_ollama_once(followup_payload, assistant_widget, chat_container)

                        elif stripped.upper().startswith("IMAGE:"):
                            img_prompt = stripped.split(":", 1)[1].strip()
                            await chat_container.mount(Static(
                                f"[dim]🧠 The user wants an image of: {img_prompt}. Generating it now.[/dim]",
                                classes="thinking-msg"
                            ))
                            if not self.gemini_api_key and not getattr(self, "proxy_url", None):
                                result_text = "No Gemini API key or proxy configured. Ask the user to run /gemini-key <key> or /proxy <url>."
                            elif not self.check_image_quota():
                                result_text = "Daily image limit reached (1/day). Try again tomorrow."
                            else:
                                assistant_widget.update(f"[dim]Generating image: {img_prompt}[/dim]")
                                chat_container.scroll_end()
                                img_bytes, err, used_model = await gemini_generate_image(self.gemini_api_key, img_prompt, proxy_url=getattr(self, "proxy_url", None))
                                if img_bytes:
                                    self.record_image_used()
                                    result_text = await self.deliver_image(img_bytes, chat_container)
                                    result_text += f" (model: {used_model})"
                                else:
                                    result_text = f"Image generation failed ({used_model}): {err}"
                            full_response = result_text
                            assistant_widget.update(full_response)

                        if full_response.strip():
                            self.conversation_history.append({"role": "assistant", "content": full_response})
                            self.save_history()
                            await self.auto_save_code_blocks(full_response, chat_container)
                    else:
                        status_bar.styles.visibility = "hidden"
                        await thinking_widget.remove()
                        err_text = await resp.text()
                        assistant_widget.update(f"[dim]Ollama error (HTTP {resp.status}): {err_text}[/dim]")
        except Exception as e:
            status_bar.styles.visibility = "hidden"
            await thinking_widget.remove()
            assistant_widget.update(f"[dim]Connection error to Ollama (localhost:11434): {str(e)}[/dim]")

        elapsed = time.time() - start_time

        if eval_duration > 0:
            tps = eval_count / (eval_duration / 1e9)
        else:
            estimated_tokens = len(full_response.split()) * 1.3
            tps = estimated_tokens / max(0.1, elapsed)

        stats_widget = Static(f"[dim]Generated in {max(0.1, elapsed):.2f}s ({tps:.1f} tok/s)[/dim]", classes="stats-msg")
        await self.mount_animated(chat_container, stats_widget)
        chat_container.scroll_end()


if __name__ == "__main__":
    app = SKCodeApp()
    app.run()
