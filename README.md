# LlamaGUI

Desktop GUI for running and chatting with **llama.cpp** (`llama-server.exe`) locally.


## Features

- **Model selection**: choose a single `.gguf` file or a folder with models.
- **Server control**: start/stop `llama-server.exe` from GUI.
- **Generation settings**: temperature, top-p, top-k, min-p, penalties, seed, max tokens.
- **Optional template/flash settings**: chat template and flash-attention mode.
- **Streaming chat UI** with safe UI updates.
- **Log tab** for server output.
- **System tab** with auto-refreshing system/GPU info.
- **Presets**: save and load configuration presets.



## Screenshots

### Settings
![Settings](https://github.com/user-attachments/assets/642d13ce-83b7-4f5e-b0f3-10d0ee71911f)

### Chat
![Chat](https://github.com/user-attachments/assets/4c3ff7a6-327e-4e82-b299-d281ac552a04)

### Log
![Log](https://github.com/user-attachments/assets/3fa649be-964a-4757-9d35-dbfc906e0079)



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



## Run

From project folder:

```bash
python main.py
```



## Quick Start

1. Download or build **llama.cpp** for Windows.
2. Create a `bin` directory in the project root (if it does not exist).
3. Place `llama-server.exe` inside the `bin` directory.
4. Open **Settings** tab.
5. Select model (`File`) or model folder (`Folder`).
6. Adjust server parameters (host/port, context, threads, etc.).
7. Click **Start Server**.
8. Open **Chat** tab, type a prompt, press **Send**.



## Notes

- Make sure the selected port is not already in use.
- Ensure `llama-server.exe` is located inside the `bin` directory.
- For GPU usage, configure the appropriate llama.cpp flags and verify your GPU drivers.



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
