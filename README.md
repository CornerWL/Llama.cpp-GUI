# LlamaGUI

Desktop GUI for running and chatting with **llama.cpp** (`llama-server.exe`) locally.

LlamaGUI provides a simple interface to:
- select GGUF models,
- configure server/generation parameters,
- start/stop the local server,
- chat via OpenAI-compatible endpoint,
- view logs and system information,
- save/load presets.

---

## Features

- **Model selection**: choose a single `.gguf` file or a folder with models.
- **Server control**: start/stop `llama-server.exe` from GUI.
- **Generation settings**: temperature, top-p, top-k, min-p, penalties, seed, max tokens.
- **Optional template/flash settings**: chat template and flash-attention mode.
- **Streaming chat UI** with safe UI updates.
- **Log tab** for server output.
- **System tab** with auto-refreshing system/GPU info.
- **Presets**: save and load configuration presets.

---

## Project Structure

- `main.py` — main GUI application (CustomTkinter).
- `config_manager.py` — config loading/saving, defaults, migration, presets.
- `server_manager.py` — server lifecycle and monitoring logic.
- `utils.py` — validation, logging setup, system/GPU helper utilities.
- `bin/` — llama.cpp binaries (`llama-server.exe`, dlls, etc.).

---

## Requirements

- **Windows 10/11** (project currently targets Windows binaries in `bin/`)
- **Python 3.8+** (3.10+ recommended)

Python packages:
- `customtkinter`
- `requests`
- `psutil` *(optional, for richer system metrics)*

Install dependencies:

```bash
pip install customtkinter requests psutil
```

> If `psutil` is not installed, the app still works and uses fallback system info.

---

## Run

From project folder:

```bash
python main.py
```

---

## Quick Start

1. Open **Settings** tab.
2. Select model (`File`) or model folder (`Folder`).
3. Adjust server parameters (host/port, context, threads, etc.).
4. Click **Start Server**.
5. Open **Chat** tab, type a prompt, press **Send**.

---

## Notes

- Make sure the selected port is free.
- Ensure `bin/llama-server.exe` exists.
- For GPU usage, configure relevant llama.cpp flags and verify your drivers.

---

## Troubleshooting

- **Server not starting**:
  - verify model path,
  - check port conflicts,
  - inspect the **Log** tab.

- **No chat response**:
  - confirm server is running,
  - verify host/port values,
  - restart the server.

- **System tab shows limited data**:
  - install `psutil` for extended metrics.
