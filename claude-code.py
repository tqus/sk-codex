#!/usr/bin/env python3
"""
sk-coder v2.2 — Textual TUI with Advanced AI Backend
Hardware: Dell Latitude 5480 (CPU-Optimized, Sub-Second Response Latency)
"""

import os
import time
import asyncio
import json
import re
import subprocess
import sys
from pathlib import Path
from textual.app import App, ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Header, Footer, Static, Input, RichLog, Button, OptionList
from textual.widgets.option_list import Option
from textual.screen import ModalScreen
from rich.markdown import Markdown
import aiohttp

SK_LOGO = """ ▐█▛█▛█▌  Welcome to SK Code!
 ▐█████▌  Run /login or /provider to get started."""

class SmolLMModal(ModalScreen):
    """Dynamic Model Selection & Control modal."""
    
    def __init__(self, current_model: str):
        super().__init__()
        self.current_model = current_model
        self.models = []

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static("[bold darkorange]═══ MODEL SELECTOR & ENGINE STATUS ═══[/bold darkorange]", classes="modal-title"),
            Static(f"[cyan]Provider: Ollama (localhost:11434)[/cyan]"),
            Static(f"[yellow]Current Model: {self.current_model}[/yellow]"),
            Static("[dim]Select an installed local model below:[/dim]"),
            OptionList(id="model-list"),
            Button("[1] Close Dashboard", id="btn_close"),
            classes="modal-box"
        )

    async def on_mount(self) -> None:
        option_list = self.query_one("#model-list", OptionList)
        option_list.add_option(Option("🔄 Fetching installed models...", id="loading"))
        
        # Fetch models from Ollama API
        installed_models = await self.fetch_installed_models()
        option_list.clear_options()
        
        if installed_models:
            self.models = installed_models
            for m in installed_models:
                prefix = "★ " if m == self.current_model else "  "
                option_list.add_option(Option(f"{prefix}{m}", id=m))
        else:
            option_list.add_option(Option("⚠️ No models found (Is Ollama running?)", id="none"))

    async def fetch_installed_models(self) -> list:
        endpoint = "http://localhost:11434/api/tags"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(endpoint, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return [model["name"] for model in data.get("models", [])]
        except Exception:
            pass
        return []

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        model_id = event.option.id
        if model_id and model_id not in ["loading", "none"]:
            self.app.model = model_id
            # Update header panel text dynamically
            header = self.app.query_one("#header-panel", Vertical)
            # Rebuild header or notify app
            chat_log = self.app.query_one("#chat-log", RichLog)
            chat_log.write(f"[bold green]✔ Active model switched to: {model_id}[/bold green]")
            self.dismiss()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss()


class SKCodeApp(App):
    """Textual TUI Application with real AI backend."""

    CSS = """
    Screen {
        background: #0d0d0d;
        color: #f0f0f0;
    }

    #header-panel {
        background: #141414;
        border-bottom: solid darkorange;
        padding: 1 2;
        height: auto;
    }

    .ascii-logo {
        color: darkorange;
        text-style: bold;
    }

    #chat-log {
        background: #0d0d0d;
        border: none;
        padding: 1 2;
    }

    #input-container {
        dock: bottom;
        background: #141414;
        border-top: solid #331f00;
        height: 3;
        padding: 0 1;
    }

    #prompt-symbol {
        color: darkorange;
        text-style: bold;
        width: 3;
        content-align: center middle;
    }

    #user-input {
        background: transparent;
        border: none;
        color: #f0f0f0;
    }

    /* Modal Styling */
    ModalScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.8);
    }

    .modal-box {
        background: #141414;
        border: solid darkorange;
        padding: 2 4;
        width: 60;
        height: auto;
        align: center middle;
    }

    .modal-title {
        color: darkorange;
        margin-bottom: 1;
        text-align: center;
    }

    OptionList {
        background: #101010;
        border: solid #333333;
        height: 8;
        margin-top: 1;
        margin-bottom: 1;
    }

    OptionList:focus {
        border: solid darkorange;
    }

    Button {
        width: 100%;
        margin-top: 1;
        background: #1f1f1f;
        color: #f0f0f0;
        border: solid #444444;
    }

    Button:hover {
        border: solid darkorange;
        color: darkorange;
    }
    """

    def __init__(self):
        super().__init__()
        self.provider = "ollama"
        self.model = "smollm"
        self.code_cache = {}

    def compose(self) -> ComposeResult:
        header_text = (
            f"[darkorange]{SK_LOGO}[/darkorange]\n\n"
            f"  Directory: [cyan]{os.path.expanduser('~')}[/cyan]\n"
            f"  Session:   [cyan]turbo-session-01[/cyan]\n"
            f"  Model:     [yellow]Dynamic Multi-Model (Turbo CPU Config)[/yellow]\n"
            f"  Version:   [cyan]0.44.0 (AI Enabled)[/cyan]\n\n"
            f"  [darkorange]✦[/darkorange] Type [cyan]/menu[/cyan] to select installed models | [cyan]/repo[/cyan] to load git repo"
        )
        
        yield Vertical(
            Static(header_text, classes="ascii-logo"),
            id="header-panel"
        )
        
        yield RichLog(id="chat-log", highlight=True, markup=True)

        yield Horizontal(
            Static("✦", id="prompt-symbol"),
            Input(placeholder="Type a message or command (e.g. /menu)...", id="user-input"),
            id="input-container"
        )

    def on_mount(self) -> None:
        chat_log = self.query_one("#chat-log", RichLog)
        chat_log.write("[darkorange]✦ Welcome to SK Code with Dynamic Model Selector![/darkorange]")
        chat_log.write("[dim]⚡ Speed Mode Enabled | Type /menu to choose installed models[/dim]\n")
        self.query_one("#user-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        user_text = event.value.strip()
        event.input.value = ""
        event.input.focus()
        
        if not user_text:
            return
        
        chat_log = self.query_one("#chat-log", RichLog)
        chat_log.write(f"[bold darkorange]✦[/bold darkorange] {user_text}")

        if user_text.lower() in ["/menu", "menu", "/provider", "provider"]:
            self.push_screen(SmolLMModal(self.model))
            chat_log.write("[cyan]✦ Model selection dashboard opened.[/cyan]")
        elif user_text.lower() in ["/login", "login"]:
            chat_log.write("[yellow]ℹ Type /menu to select active local model.[/yellow]")
        elif user_text.lower() in ["/repo", "repo"]:
            chat_log.write("[yellow]ℹ Usage: /repo <github_url> to clone and index repository.[/yellow]")
        else:
            self.run_worker(self.generate_response(user_text, chat_log))

    async def generate_response(self, prompt: str, chat_log: RichLog) -> None:
        chat_log.write(f"[green]⏳ Generating via {self.provider.upper()} ({self.model})...[/green]")
        start_time = time.time()
        
        try:
            p_lower = prompt.lower()
            is_coding_request = any(k in p_lower for k in [
                "code", "script", "function", "write", "python", "bug", "fix", 
                "error", "api", "class", "parse", "json", "sql", "html", "css", 
                "javascript", "js", "bash", "shell", "webpage", "website", "site", 
                "landing", "portfolio", "create", "app", "build"
            ])

            if is_coding_request:
                response_text = await self.generate_code(prompt)
                
                if any(k in p_lower for k in ["html", "webpage", "website", "site", "landing", "portfolio"]):
                    filename = "index.html"
                    lang = "html"
                    file_content = response_text if response_text.startswith("<!DOCTYPE") else self.generate_html_template(prompt, response_text)
                    
                elif any(k in p_lower for k in ["python", "py", "script"]):
                    filename = "script.py"
                    lang = "python"
                    file_content = response_text
                    
                elif any(k in p_lower for k in ["javascript", "js", "react"]):
                    filename = "app.js"
                    lang = "javascript"
                    file_content = response_text
                    
                else:
                    filename = "output.txt"
                    lang = "text"
                    file_content = response_text
                
                try:
                    filepath = os.path.join(os.getcwd(), filename)
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(file_content)
                    save_msg = f"[bold green]✔ Saved to `{filename}`[/bold green]"
                    self.code_cache[filename] = file_content
                except Exception as e:
                    save_msg = f"[bold red]✖ Auto-save failed: {e}[/bold red]"

                preview = file_content[:400].replace("```", "")
                response_md = f"### Generated {lang.upper()}\n```{lang}\n{preview}\n...\n```\n{save_msg}"
                chat_log.write(Markdown(response_md))
            else:
                response_text = await self.query_llm(prompt)
                chat_log.write(f"[cyan]{response_text}[/cyan]")

        except Exception as e:
            chat_log.write(f"[bold red]✖ Error: {str(e)}[/bold red]")
            chat_log.write("[yellow]ℹ Start Ollama: `ollama serve`[/yellow]")

        elapsed = time.time() - start_time
        chat_log.write(f"[dim cyan]⚡ Generated in {max(0.15, elapsed):.2f}s[/dim cyan]\n")

    async def query_llm(self, prompt: str) -> str:
        """Query currently chosen model via Ollama."""
        return await self.query_ollama(prompt)

    async def query_ollama(self, prompt: str) -> str:
        """Query Ollama local LLM with performance and latency optimizations."""
        endpoint = "http://localhost:11434/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.2,       # Lower temp for faster token sampling
                "top_p": 0.8,
                "num_predict": 512,       # Restrict max token length for quick execution
                "num_ctx": 2048,          # Keep context overhead minimal on CPU
            }
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(endpoint, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("response", "No response generated.").strip()
                    elif resp.status == 404:
                        return f"⚠️ Model '{self.model}' not found. Run: `ollama pull {self.model}`"
                    else:
                        return f"Ollama error (status {resp.status}). Is it running at localhost:11434?"
        except asyncio.TimeoutError:
            return "⏱️ Request timeout. Ollama may be busy. Try again."
        except Exception as e:
            return f"Connection error: {str(e)}. Ensure Ollama is running."

    async def generate_code(self, prompt: str) -> str:
        """Generate code with enhanced context awareness."""
        code_prompt = f"""Generate clean, production-ready code for the following request. Include comments where needed.
        
Request: {prompt}

Provide ONLY the code, no explanations or markdown fencing."""
        
        response = await self.query_llm(code_prompt)
        
        # Clean up response if it has markdown code blocks
        if "```" in response:
            match = re.search(r"```(?:\w+)?\n(.*?)\n```", response, re.DOTALL)
            if match:
                response = match.group(1)
        
        return response.strip()

    def generate_html_template(self, prompt: str, ai_response: str) -> str:
        """Generate a clean HTML template with AI code insights."""
        summary = ai_response[:150].replace("<", "&lt;").replace(">", "&gt;")
        safe_prompt = prompt[:40].replace("<", "&lt;").replace(">", "&gt;")
        
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SK Code Project</title>
    <style>
        :root {{
            --bg-color: #0f1115;
            --card-bg: #181c24;
            --accent: #ff8c00;
            --text-main: #f0f0f0;
            --text-muted: #8892b0;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }}
        body {{ background-color: var(--bg-color); color: var(--text-main); line-height: 1.6; display: flex; flex-direction: column; min-height: 100vh; }}
        header {{ background: var(--card-bg); border-bottom: 2px solid var(--accent); padding: 1rem 2rem; display: flex; justify-content: space-between; align-items: center; }}
        .logo {{ color: var(--accent); font-weight: bold; font-size: 1.2rem; }}
        nav a {{ color: var(--text-muted); text-decoration: none; margin-left: 1.5rem; transition: color 0.2s; }}
        nav a:hover {{ color: var(--accent); }}
        main {{ flex: 1; max-width: 960px; margin: 3rem auto; padding: 0 2rem; width: 100%; }}
        .hero {{ background: var(--card-bg); border: 1px solid #2a3241; border-radius: 8px; padding: 3rem; text-align: center; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }}
        h1 {{ font-size: 2.5rem; margin-bottom: 1rem; color: #fff; }}
        h1 span {{ color: var(--accent); }}
        p {{ color: var(--text-muted); margin-bottom: 2rem; font-size: 1.1rem; }}
        .ai-notes {{ background: #0d0d0d; border-left: 3px solid var(--accent); padding: 1rem; margin: 2rem 0; font-size: 0.95rem; }}
        .btn {{ background: var(--accent); color: #000; border: none; padding: 0.8rem 2rem; font-weight: bold; border-radius: 4px; cursor: pointer; transition: opacity 0.2s; }}
        .btn:hover {{ opacity: 0.9; }}
        footer {{ text-align: center; padding: 1.5rem; background: var(--card-bg); border-top: 1px solid #2a3241; color: var(--text-muted); font-size: 0.9rem; }}
    </style>
</head>
<body>
    <header>
        <div class="logo">⚡ SK Web Studio</div>
        <nav>
            <a href="#home">Home</a>
            <a href="#features">Features</a>
            <a href="#contact">Contact</a>
        </nav>
    </header>
    <main>
        <section class="hero">
            <h1>Web Solution for <span>{safe_prompt}</span></h1>
            <p>AI-Generated by SK Code Engine • Model: {self.model}</p>
            <button class="btn" onclick="triggerAction()">Explore Project</button>
            <div class="ai-notes">
                <strong>AI Generated:</strong> {summary}
            </div>
        </section>
    </main>
    <footer>
        <p>&copy; 2026 SK Code Engine. Powered by Ollama.</p>
    </footer>
    <script>
        function triggerAction() {{
            alert("Interactive component initialized successfully!");
        }}
    </script>
</body>
</html>"""


if __name__ == "__main__":
    app = SKCodeApp()
    app.run()
