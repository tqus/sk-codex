# SK-Codex

SK-Codex is a local-first Terminal User Interface (TUI) coding assistant built with [Textual](https://textual.textualize.io/) and powered by local LLMs via [Ollama](https://ollama.com/). Designed for speed, privacy, and low-latency code generation, it runs entirely on local hardware with real-time system monitoring, persistent chat history, and built-in developer workflows.

---

## Features

* **Lightweight TUI Architecture:** Fully interactive terminal interface built with Textual, featuring split-pane layouts and keyboard shortcuts.
* **Local LLM Integration:** Connects directly to Ollama (`localhost:11434`), optimized for high tokens-per-second performance with models like `qwen2.5-coder:1.5b`.
* **Dynamic Effort Control:** Adjust reasoning and thinking depth dynamically (`low`, `med`, `high`).
* **Real-Time System Metrics:** Live sidebar monitoring CPU usage, RAM utilization, and disk status via `psutil`.
* **Automatic Code Preservation:** Automatically extracts markdown code blocks from assistant responses and saves them into a local `documents/` directory.
* **Persistent History:** Automatically saves conversation logs to disk (`sk_codex_history.json`) across sessions.

---

## Installation

1. **Clone the repository:**
```bash
git clone https://github.com/tqus/sk-codex.git
cd sk-codex

```


2. **Create and activate a virtual environment:**
```bash
python3 -m venv venv
source venv/bin/activate

```


3. **Install dependencies:**
```bash
pip install -r requirements.txt

```


4. **Ensure Ollama is running locally:**
```bash
ollama pull qwen2.5-coder:1.5b
ollama serve

```



---

## Usage

Launch the application by running the main entry point:

```bash
python sk_codex.py

```

### Keyboard Shortcuts

* **`Ctrl + C`**: Quit the application
* **`Ctrl + L`**: Clear conversation history and reset log
* **`F2`**: Toggle the system resource sidebar

### Built-in Commands

Type these commands directly into the prompt input:

| Command | Description |
| --- | --- |
| `/help` | Display available command manual |
| `/menu` | Open model selection options |
| `/effort [level]` | Set reasoning effort (`low`, `med`, `high`) |
| `/skills` | Access developer skills toolkit |
| `/clear` | Clear chat log and memory |
| `/exit` | Exit the application cleanly |

---

## Project Structure

* `sk_codex.py`: Main application script containing the Textual app layout, system monitor widget, and Ollama integration worker.
* `requirements.txt`: Python package dependencies (`textual`, `psutil`, `httpx`).
* `documents/`: Directory where extracted code snippets are automatically stored.
* `sk_codex_history.json`: Local storage file for chat conversation history.

---

## License

Distributed under the MIT License. See `LICENSE` for more details.
