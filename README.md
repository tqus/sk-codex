# SK-Coder

SK-Coder is an ultra-fast, local-first Terminal User Interface (TUI) coding assistant built with [Textual](https://textual.textualize.io/) and powered by local LLMs via [Ollama](https://ollama.com/). Engineered specifically for low-resource hardware profiles (such as 8GB RAM laptops), it delivers low-latency code generation, real-time system monitoring, persistent session history, and built-in developer utility workflows.

---

## Key Features

* **Lightweight TUI Architecture:** Built using Textual, providing a smooth, responsive terminal interface complete with an interactive command autocomplete palette.
* **Local LLM Integration:** Seamlessly connects to Ollama (`localhost:11434`), optimized for models like `qwen2:0.5b` and `qwen2.5-coder:1.5b` to maximize tokens-per-second performance on constrained hardware.
* **Dynamic Effort Control:** Adjust reasoning depth on the fly (`low`, `med`, `high`) to balance response speed and analytical depth.
* **Built-In Developer Skills Toolkit:** Instant execution of common repository tasks, including codebase scanning, security credential checks, statistics calculation, and bytecode cleanups.
* **Automatic Code Preservation:** Automatically extracts markdown code snippets from assistant responses and saves them timestamped into a local `documents/` directory.
* **Real-Time System Monitoring:** Integrated hardware sidebar tracking live CPU usage, memory consumption, and thermal sensors.
* **Persistent Local Sessions:** Automatically saves conversation logs (`sk_coder_history.json`) and user login states locally.

---

## System Requirements

* **OS:** Linux / macOS / Windows (WSL)
* **Python:** 3.10 or higher
* **Backend:** [Ollama](https://ollama.com/) running locally with desired models pulled.

---

## Installation

1. **Clone the repository and navigate to the project directory:**
   ```bash
   git clone [https://github.com/your-username/sk-coder.git](https://github.com/your-username/sk-coder.git)
   cd sk-coder
