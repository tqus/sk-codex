#!/usr/bin/env python3
"""
SK-Coder / SK Cortex CLI — Claude Code style terminal UI (Standalone).
Expanded modal system prompt switcher with Skills, NPX tool integration,
and Groq API backend integration (using openai/gpt-oss-20b).
"""

import os
import sys
import time
import asyncio
import json
import subprocess
import re
import urllib.parse
from pathlib import Path
import psutil
import aiohttp

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.live import Live

console = Console()

HISTORY_FILE = Path("sk_coder_history.json")
CONFIG_FILE = Path("sk_coder_config.json")
IDENTITY_FILE = Path("sk_coder_identity.json")
DOCUMENTS_DIR = Path("documents")
DOCUMENTS_DIR.mkdir(exist_ok=True)
SKILLS_DIR = Path("skills")
SKILLS_DIR.mkdir(exist_ok=True)

GROQ_API_KEY = "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"

USER_PROFILE = {
    "name": "Saad Kashif",
    "dob": "June 7, 1981",
    "device_name": "OSINT",
    "interests": [
        "Cybersecurity (TryHackMe, Burp Suite)",
        "Software Development & Version Control (GitHub, Replit, GCP, Cloudflare, Zoho Creator)",
        "Gaming & Streaming (Roblox, GeForce NOW, Steam, Twitch)",
        "Operating Systems & Linux (Arch, Zorin, Kali Linux, riced setups)",
        "Productivity & AI Tools (Notion, xAI Grok, SocialBee)"
    ],
    "family": "Mother and Sister",
    "recent_activities": "Traveled to Islamabad, visited Burj Khalifa and Sharjah Nesto supermarket."
}

SYSTEM_MODALS = {
    "opus 5": (
        "You are Claude Opus 5, an advanced AI model for demanding reasoning, coding, and long-horizon agentic work. "
        f"The user is {USER_PROFILE['name']} (born {USER_PROFILE['dob']}), operating on local device 'OSINT'. "
        "You excel at end-to-end software engineering, deep code reviews, structural analysis, and precise technical execution. "
        "You have direct access to run shell commands, create or edit local files, execute npx packages, and utilize custom local skills."
    ),
    "sonnet 5": (
        "You are Claude Sonnet 5, a balanced powerhouse optimized for lightning-fast coding, clear technical writing, "
        f"and structured problem-solving. You are collaborating with {USER_PROFILE['name']} on the 'OSINT' environment workspace. "
        "Provide direct, highly efficient code snippets, system administration scripts, and architectural insights."
    ),
    "kimi k3": (
        "You are Kimi K3, an advanced language model renowned for deep context comprehension, long-form content generation, "
        f"and precise coding logic. You are assisting {USER_PROFILE['name']} on the 'OSINT' machine. "
        "Be articulate, deeply thorough, and clear in explaining complex technological or security concepts."
    ),
    "chatgpt": (
        "You are ChatGPT (GPT-4o architecture), a versatile conversational assistant. You are assisting "
        f"{USER_PROFILE['name']} on the local 'OSINT' setup. You are adaptable, creative, efficient at writing code, "
        "debugging scripts, and resolving general inquiries with maximum clarity."
    ),
    "fable 5": (
        "You are Fable 5, an advanced autonomous local agent operating directly on the user's computer (device 'OSINT'). "
        f"The user is {USER_PROFILE['name']} (born {USER_PROFILE['dob']}), with expertise in cybersecurity, Linux, and development. "
        "You are an expert creative technologist and Three.js developer."
    ),
    "secops": (
        "You are SecOps-AI, an elite cybersecurity and defensive engineering assistant specialized in penetration testing concepts, "
        "secure code hardening, Linux administration, and network analysis. You assist Saad Kashif on the 'OSINT' system workspace."
    )
}

def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return default

def save_json(path: Path, data):
    try:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass

def load_identity():
    return load_json(IDENTITY_FILE, {})

def save_identity(data):
    save_json(IDENTITY_FILE, data)

def load_config():
    cfg = load_json(CONFIG_FILE, {
        "modal": "sonnet 5",
        "effort": "low",
        "use_context": True,
        "display_name": None
    })
    if cfg.get("modal") not in SYSTEM_MODALS:
        cfg["modal"] = "sonnet 5"
        save_json(CONFIG_FILE, cfg)
    return cfg

def save_config(cfg):
    save_json(CONFIG_FILE, cfg)

def load_history():
    return load_json(HISTORY_FILE, [])

def save_history(history):
    save_json(HISTORY_FILE, history)


def run_shell_command(cmd_str: str) -> str:
    try:
        res = subprocess.run(
            cmd_str, shell=True, capture_output=True, text=True, timeout=120
        )
        output = res.stdout.strip()
        error = res.stderr.strip()
        result_str = ""
        if output:
            result_str += f"STDOUT:\n{output}\n"
        if error:
            result_str += f"STDERR:\n{error}\n"
        if not result_str:
            result_str = "Command executed successfully with no output."
        return result_str
    except Exception as e:
        return f"Error executing command: {str(e)}"


class SKCoderCLI:
    def __init__(self):
        self.config = load_config()
        self.current_modal = self.config.get("modal", "sonnet 5")
        self.effort_level = self.config.get("effort", "low")
        self.use_context = self.config.get("use_context", True)
        self.history = load_history()
        self.skip_context_once = False

        identity = load_identity()
        self.display_name = identity.get("display_name") or self.config.get("display_name")
        if not self.display_name:
            console.clear()
            name = console.input("Enter display name for this device (OSINT): ").strip() or USER_PROFILE["name"]
            self.display_name = name
            self.config["display_name"] = name
            save_identity({"display_name": name, "acknowledged": True})
            save_config(self.config)

    def print_header(self):
        console.clear()
        cwd = os.getcwd()
        mem = psutil.virtual_memory()
        cpu = psutil.cpu_percent()
        
        header_md = (
            f"[#4db8ff]└─$[/] [#4db8ff]sk-cortex / standalone[/] [dim]v5.1 (Groq Engine)[/dim]\n\n"
            f"[#d97757]  ████████ [/] [bold white]Active Modal: {self.current_modal}[/bold white] [dim]· Device: OSINT · User: {self.display_name}[/dim]\n"
            f"[#d97757]████ ██ ████[/] [dim]Effort: {self.effort_level} · Working Dir: {cwd}[/dim]\n"
            f"[#d97757] █████████ [/] [dim]CPU: {cpu}% · RAM: {mem.percent}% ({mem.used // (1024**2)}MB / {mem.total // (1024**2)}MB)[/dim]\n"
            f"[#d97757] █ █  █ █ [/] [dim]Type /listmodals, /skills, or /npx <package> to run tools.[/dim]"
        )
        console.print(Panel(header_md, border_style="cyan", padding=(1, 2)))

    def save_state(self):
        self.config["modal"] = self.current_modal
        self.config["effort"] = self.effort_level
        self.config["use_context"] = self.use_context
        self.config["display_name"] = self.display_name
        save_config(self.config)
        save_history(self.history)

    def get_multiline_input(self) -> str:
        console.print("fable> ", end="")
        sys.stdout.flush()
        
        lines = []
        try:
            while True:
                line = sys.stdin.readline()
                if not line:
                    break
                stripped_line = line.rstrip("\r\n")
                if not lines and stripped_line == "":
                    return ""
                
                lines.append(stripped_line)
                import select
                r, _, _ = select.select([sys.stdin], [], [], 0.05)
                if not r:
                    break
        except (KeyboardInterrupt, EOFError):
            raise
            
        return "\n".join(lines).strip()

    async def chat_loop(self):
        self.print_header()

        while True:
            try:
                loop = asyncio.get_running_loop()
                user_input = await loop.run_in_executor(None, self.get_multiline_input)
            except (KeyboardInterrupt, EOFError):
                console.print("\nInterrupted. Saving session...")
                self.save_state()
                sys.exit(0)

            if not user_input:
                continue

            if user_input.startswith("/"):
                await self.handle_command(user_input)
            else:
                await self.process_ai_turn(user_input)

    async def handle_command(self, raw_cmd: str):
        parts = raw_cmd.split(maxsplit=1)
        cmd = parts[0][1:].lower().replace("-", "_")
        args_str = parts[1].strip() if len(parts) > 1 else ""

        if cmd in ["exit", "quit"]:
            self.save_state()
            console.print("Goodbye!")
            sys.exit(0)
        elif cmd == "help":
            console.print(Panel(
                "Available Commands:\n"
                "  /help - Show help menu\n"
                "  /modal <name> - Switch modal persona (sonnet 5, kimi k3, chatgpt, opus 5, fable 5, secops)\n"
                "  /listmodals - List all available system modals\n"
                "  /skills - List available local skills in ./skills\n"
                "  /npx <pkg> [args] - Run any npx package instantly\n"
                "  /effort <low|med|high> - Set reasoning depth\n"
                "  /context - Toggle persistent chat history\n"
                "  /clear - Clear history\n"
                "  /sys - Show resource stats\n"
                "  /shell <cmd> - Run a local terminal command\n"
                "  /exit - Quit app",
                title="Command Reference", border_style="cyan"
            ))
        elif cmd == "modal":
            if args_str:
                target_modal = args_str.lower()
                if target_modal in SYSTEM_MODALS:
                    self.current_modal = target_modal
                    self.save_state()
                    console.print(f"Switched active modal persona to: {self.current_modal}")
                else:
                    console.print(f"Unknown modal '{target_modal}'. Available options: {list(SYSTEM_MODALS.keys())}")
            else:
                console.print(f"Current modal: {self.current_modal}. Use /listmodals to see options.")
        elif cmd == "listmodals":
            modal_list_text = "\n".join(f"- {name}: {prompt[:65]}..." for name, prompt in SYSTEM_MODALS.items())
            console.print(Panel(modal_list_text, title="Configured System Modals", border_style="cyan"))
        elif cmd == "skills":
            skills_files = [f.name for f in SKILLS_DIR.iterdir()] if SKILLS_DIR.exists() else []
            if skills_files:
                skills_text = "\n".join(f"• {s}" for s in skills_files)
            else:
                skills_text = "No custom skills found in ./skills directory. Add scripts or prompt files here."
            console.print(Panel(skills_text, title="Loaded Local Skills", border_style="cyan"))
        elif cmd == "npx":
            if not args_str:
                console.print("Usage: /npx <package-name> [arguments]")
            else:
                npx_cmd = f"npx {args_str}"
                console.print(f"[dim]Running: {npx_cmd}[/dim]")
                output = run_shell_command(npx_cmd)
                console.print(Panel(output, title="NPX Execution Result", border_style="cyan"))
        elif cmd == "clear":
            self.history.clear()
            if HISTORY_FILE.exists():
                HISTORY_FILE.unlink()
            console.print("History cleared.")
        elif cmd == "sys":
            mem = psutil.virtual_memory()
            cpu = psutil.cpu_percent()
            console.print(Panel(f"Device: OSINT\nCPU Usage: {cpu}%\nRAM Usage: {mem.percent}%", title="System Status"))
        elif cmd == "shell":
            if not args_str:
                console.print("Usage: /shell <command>")
            else:
                output = run_shell_command(args_str)
                console.print(Panel(output, title="Shell Output", border_style="cyan"))
        else:
            await self.process_ai_turn(raw_cmd)

    async def process_ai_turn(self, prompt: str):
        self.history.append({"role": "user", "content": prompt})
        
        system_prompt = SYSTEM_MODALS.get(self.current_modal, SYSTEM_MODALS["sonnet 5"])
        
        # Append available skills context if any exist
        if SKILLS_DIR.exists():
            skill_files = [f.name for f in SKILLS_DIR.iterdir() if f.is_file()]
            if skill_files:
                system_prompt += f"\nAvailable local skills in ./skills: {', '.join(skill_files)}"

        # Format messages for OpenAI-compatible Groq API (system message included as role: system)
        groq_messages = [{"role": "system", "content": system_prompt}]
        if self.use_context:
            groq_messages.extend(self.history)
        else:
            groq_messages.append({"role": "user", "content": prompt})
        
        full_response = ""
        start_time = time.time()
        console.print()

        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "openai/gpt-oss-20b",
            "messages": groq_messages,
            "max_tokens": 4096,
            "stream": True
        }

        try:
            with Live(console=console, refresh_per_second=60) as live:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers=headers,
                        json=payload
                    ) as resp:
                        if resp.status != 200:
                            err_text = await resp.text()
                            console.print(f"[red]Groq API Error ({resp.status}): {err_text}[/red]")
                            return

                        async for line in resp.content:
                            line_str = line.decode("utf-8").strip()
                            if line_str.startswith("data: "):
                                data_str = line_str[6:]
                                if data_str == "[DONE]":
                                    break
                                try:
                                    event_data = json.loads(data_str)
                                    choices = event_data.get("choices", [])
                                    if choices:
                                        delta = choices[0].get("delta", {})
                                        if "content" in delta and delta["content"]:
                                            full_response += delta["content"]
                                            live.update(Markdown(full_response))
                                except json.JSONDecodeError:
                                    pass
        except KeyboardInterrupt:
            console.print("\nInterrupted by user.")
            return
        except Exception as e:
            console.print(f"\n[red]Connection error: {e}[/red]")
            return

        elapsed = time.time() - start_time
        console.print(f"\n{elapsed:.2f}s\n")
        self.history.append({"role": "assistant", "content": full_response})
        self.save_state()


def main():
    cli = SKCoderCLI()
    try:
        asyncio.run(cli.chat_loop())
    except KeyboardInterrupt:
        console.print("\nExiting...")
        sys.exit(0)


if __name__ == "__main__":
    main()
