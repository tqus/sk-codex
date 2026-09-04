# SK Code v2.2 — AI-Powered Code Generation TUI

A terminal UI for rapid code generation with **Claude**, **Ollama**, or **Hugging Face** backends.

## Setup

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Choose Your AI Provider

#### **Option A: Claude API (Recommended)**
```bash
export ANTHROPIC_API_KEY=sk-ant-xxxxx
python sk_code_ai.py
# Select [2] Claude API in /menu
```

#### **Option B: Ollama (Local, Fastest)**
```bash
# Install Ollama from https://ollama.ai
# Pull a model:
ollama pull neural-chat

# In one terminal:
ollama serve

# In another:
python sk_code_ai.py
# Select [1] Ollama in /menu
```

#### **Option C: Hugging Face (Cloud)**
```bash
export HF_TOKEN=hf_xxxxx
python sk_code_ai.py
# Select [3] Hugging Face in /menu
```

## Usage

```bash
python sk_code_ai.py
```

### Commands
- `/menu` — Switch AI provider
- `/repo <url>` — Load GitHub repo (coming soon)

### Code Generation
Just type requests like:
- `write a python script to parse JSON`
- `create a landing page for a SaaS app`
- `fix this bug: ...`
- `html todo app with tailwind`

The app auto-detects the language and saves code to disk.

## Features

✅ **Multi-backend support** — Claude, Ollama, Hugging Face  
✅ **Auto-save code** — Generated files saved instantly  
✅ **Smart language detection** — Python, JS, HTML/CSS  
✅ **Production-ready output** — Clean, commented code  
✅ **Fast inference** — Sub-second responses (Ollama) or streaming (Claude)  

## Keyboard Shortcuts
- `Ctrl+C` — Exit  
- `Tab` — Move focus  

## Troubleshooting

**Ollama not responding:**
```bash
# Ensure Ollama is running
ollama serve

# Check if model is installed
ollama list

# Pull a model if missing
ollama pull neural-chat
```

**HF_TOKEN errors:**
```bash
export HF_TOKEN=hf_xxxxx  # Get from huggingface.co/settings/tokens
```

**Claude API errors:**
```bash
export ANTHROPIC_API_KEY=sk-ant-xxxxx  # Get from console.anthropic.com
```

---

**SK Code Engine** — Built for rapid prototyping and code generation.
