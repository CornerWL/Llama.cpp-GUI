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

---

## License

Add your preferred license file (e.g. MIT) if you plan to publish this project.

---

# Русская версия (ниже)

LlamaGUI — это настольный GUI для локального запуска **llama.cpp** (`llama-server.exe`) и общения с моделью.

Приложение позволяет:
- выбирать GGUF-модели,
- настраивать параметры сервера и генерации,
- запускать/останавливать локальный сервер,
- общаться через OpenAI-совместимый endpoint,
- смотреть логи и системную информацию,
- сохранять/загружать пресеты.

---

## Возможности

- **Выбор модели**: отдельный `.gguf` файл или папка с моделями.
- **Управление сервером**: запуск/остановка `llama-server.exe` из GUI.
- **Параметры генерации**: temperature, top-p, top-k, min-p, penalties, seed, max tokens.
- **Дополнительно**: chat template и flash-attention.
- **Потоковый чат** с безопасным обновлением UI.
- **Вкладка логов** для вывода сервера.
- **Вкладка System** с автообновлением данных о системе/GPU.
- **Пресеты**: сохранение и загрузка наборов настроек.

---

## Структура проекта

- `main.py` — основное GUI-приложение (CustomTkinter).
- `config_manager.py` — конфиг, значения по умолчанию, миграция, пресеты.
- `server_manager.py` — логика жизненного цикла сервера и мониторинг.
- `utils.py` — валидация, логирование, утилиты по системе/GPU.
- `bin/` — бинарники llama.cpp (`llama-server.exe`, dll и т.д.).

---

## Требования

- **Windows 10/11** (в проекте используются Windows-бинарники в `bin/`)
- **Python 3.8+** (рекомендуется 3.10+)

Пакеты Python:
- `customtkinter`
- `requests`
- `psutil` *(опционально, для более подробной системной статистики)*

Установка зависимостей:

```bash
pip install customtkinter requests psutil
```

> Если `psutil` не установлен, приложение продолжит работать с fallback-данными.

---

## Запуск

Из папки проекта:

```bash
python main.py
```

---

## Быстрый старт

1. Откройте вкладку **Settings**.
2. Выберите модель (`File`) или папку с моделями (`Folder`).
3. Настройте параметры сервера (host/port, context, threads и т.д.).
4. Нажмите **Start Server**.
5. Перейдите во вкладку **Chat**, введите запрос и нажмите **Send**.

---

## Примечания

- Убедитесь, что выбранный порт свободен.
- Проверьте наличие `bin/llama-server.exe`.
- Для GPU-ускорения настройте соответствующие флаги llama.cpp и драйверы.

---

## Решение проблем

- **Сервер не запускается**:
  - проверьте путь к модели,
  - убедитесь, что порт не занят,
  - смотрите вкладку **Log**.

- **Нет ответа в чате**:
  - убедитесь, что сервер запущен,
  - проверьте host/port,
  - перезапустите сервер.

- **Вкладка System показывает мало данных**:
  - установите `psutil` для расширенной статистики.

---

## Лицензия

Добавьте файл лицензии (например, MIT), если планируете публиковать проект.
