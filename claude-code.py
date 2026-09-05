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
from pathlib import Path
import psutil
from textual.app import App, ComposeResult
from textual.containers import Container, Vertical, Horizontal, VerticalScroll
from textual.widgets import Static, Input, Button, OptionList
from textual.widgets.option_list import Option
from textual.screen import ModalScreen
import aiohttp

MASTER_COMMANDS = [
    ("/menu", "Open model selector dashboard"),
    ("/skills", "List and execute built-in utility skills"),
    ("/login", "Create or manage a one-time session account"),
    ("/effort", "Set reasoning/thinking effort level (low, med, high)"),
    ("/clear", "Clear chat conversation log and memory file"),
    ("/save", "Manually save current session history to disk"),
    ("/help", "Display available commands and manual"),
    ("/about", "Display SK-Coder engine version details"),
    ("/sys", "Display full system metrics summary"),
    ("/cpu", "Check current CPU usage breakdown"),
    ("/ram", "Check RAM and memory allocation"),
    ("/temp", "Check hardware and CPU thermal sensors"),
    ("/workspace", "Show absolute working directory path"),
    ("/list", "List files in current working directory"),
    ("/run", "Execute current script or project file"),
    ("/lint", "Run static code analysis and linting"),
    ("/format", "Format source code files automatically"),
    ("/qwen", "Switch directly to Qwen Coder 1.5B (Speed Optimized)"),
    ("/tiny", "Switch directly to Qwen 0.5B (Ultra-fast fallback)"),
    ("/time", "Display current local time and date"),
    ("/shell", "Execute a raw shell command string"),
    ("/exit", "Quit the application cleanly")
]

HISTORY_FILE = Path("sk_coder_history.json")
USER_FILE = Path("sk_coder_user.json")


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
    """Textual TUI Application matching exact Claude Code ASCII logo, persistent history, and built-in skills."""

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

    .stats-msg {
        color: #888;
        margin-bottom: 1;
    }

    .system-msg {
        color: #888;
        margin-top: 1;
        margin-bottom: 1;
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
        user_str = f" · User: {self.logged_in_user}" if self.logged_in_user else ""
        return (
            f"[#4db8ff]└─$[/] [#4db8ff]claude[/]\n"
            f"[#e57053]  █████████[ [/] [bold white]Claude Code[/bold white] [dim]v2.1.261{user_str}[/dim]\n"
            f"[#e57053]████ ███ ████[/] [dim]fable 5.1 · API Usage Billing[/dim]\n"
            f"[#e57053]█ █████████ █[/] [dim]{cwd}[/dim]\n"
            f"[#e57053]   █    █[/]\n"
        )

    def update_header(self) -> None:
        self.query_one(".ascii-logo", Static).update(self._build_header_text())

    async def on_mount(self) -> None:
        chat_container = self.query_one("#chat-container", VerticalScroll)
        
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
        if not raw_text:
            await chat_container.mount(Static(f"[dim]>[/dim] /{cmd_id}", classes="user-msg"))
        else:
            await chat_container.mount(Static(f"[dim]>[/dim] {raw_text}", classes="user-msg"))
        
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
            await chat_container.mount(Static("[dim]SK-Coder Command Manual: Type '/skills' for built-in tools, '/login' for accounts, '/effort' for reasoning level.[/dim]", classes="system-msg"))
        elif cmd_id in ["about", "version"]:
            await chat_container.mount(Static("[dim]SK-Coder v3.9.8 — Exact Claude Code Layout & Low-Latency 8GB Optimization.[/dim]", classes="system-msg"))
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
            try:
                filepath.write_text(code_content.strip(), encoding="utf-8")
                await chat_container.mount(Static(f"[dim]✓ Auto-saved [{lang_clean}] to documents/{filename}[/dim]", classes="system-msg"))
            except Exception as e:
                await chat_container.mount(Static(f"[dim]Failed to auto-save code block: {e}[/dim]", classes="system-msg"))
        chat_container.scroll_end()

    async def stream_response(self, prompt: str, chat_container: VerticalScroll) -> None:
        status_bar = self.query_one("#status-bar", Static)
        status_bar.styles.visibility = "visible"
        status_bar.update(f"  [dim]{self.model} (effort: {self.effort_level}) generating...[/dim]")

        await chat_container.mount(Static(f"[dim]>[/dim] {prompt}", classes="user-msg"))
        
        num_predict_map = {"low": 96, "med": 192, "high": 384}
        max_tokens = num_predict_map.get(self.effort_level, 192)

        thinking_widget = Static("[dim]Thinking process: analyzing query...[/dim]", classes="thinking-msg")
        assistant_widget = Static("[dim]Generating response...[/dim]", classes="assistant-msg")
        
        await chat_container.mount(thinking_widget)
        await chat_container.mount(assistant_widget)
        chat_container.scroll_end()

        self.conversation_history.append({"role": "user", "content": prompt})
        recent_history = self.conversation_history[-2:]

        endpoint = "http://localhost:11434/api/chat"
        
        effort_prompts = {
            "low": "Give a direct, concise answer immediately.",
            "med": "Think step-by-step briefly in <think> tags, then provide a clear answer.",
            "high": "Provide rigorous step-by-step reasoning enclosed in <think> tags before delivering the comprehensive code response."
        }
        
        system_prompt = (
            f"You are an ultra-fast coding assistant. {effort_prompts.get(self.effort_level, '')}"
        )
        if self.logged_in_user:
            system_prompt += f" Current user session: {self.logged_in_user}."

        messages = [{"role": "system", "content": system_prompt}] + recent_history

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
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
        await chat_container.mount(stats_widget)
        chat_container.scroll_end()


if __name__ == "__main__":
    app = SKCodeApp()
    app.run()
