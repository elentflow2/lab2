# MP3 Tracker v7 - Desktop Application

## Сборка десктопного приложения

Приложение успешно упаковано в standalone executable с помощью PyInstaller.

### Структура проекта:
- `mp3tracker_v7.py` - исходный код приложения
- `mp3tracker_v7.spec` - конфигурация сборки PyInstaller
- `dist/mp3tracker_v7` - готовый исполняемый файл (Linux)
- `build/` - временные файлы сборки

---

## 🪟 ИНСТРУКЦИЯ ДЛЯ WINDOWS

**Важно:** PyInstaller создает исполняемые файлы только для той ОС, на которой запущен. 
Поскольку сборка происходила на Linux, в папке `dist/` находится версия для Linux.

### Чтобы получить .exe для Windows:

#### Шаг 1: Установите Python на Windows
1. Скачайте Python с https://www.python.org/downloads/
2. **Обязательно** отметьте галочку ✅ "Add Python to PATH" при установке

#### Шаг 2: Установите зависимости
Откройте Command Prompt (cmd) или PowerShell и выполните:
```cmd
pip install customtkinter telethon pygame mutagen pyinstaller
```

#### Шаг 3: Скопируйте файл приложения
Скопируйте файл `mp3tracker_v7.py` из этого репозитория в папку на вашем компьютере.

#### Шаг 4: Запустите сборку
В командной строке перейдите в папку с файлом и выполните:
```cmd
pyinstaller --onefile --windowed --name mp3tracker_v7 --hidden-import telethon --hidden-import telethon.tl.types --hidden-import mutagen.id3 --hidden-import customtkinter --hidden-import pygame mp3tracker_v7.py
```

#### Шаг 5: Готово!
Исполняемый файл появится в папке `dist\mp3tracker_v7.exe`

Можете копировать этот `.exe` файл на любой компьютер с Windows и запускать без установки Python!

---

### Как запустить текущую версию (Linux):
```bash
./dist/mp3tracker_v7
```

### Особенности сборки:
- **Формат**: Single-file executable (один файл)
- **Режим**: Windowed (без консольного окна)
- **Размер**: ~46 MB
- **Платформа**: Текущая ОС (Linux или Windows)
- **Зависимости**: Встроены в executable (customtkinter, telethon, pygame, mutagen)

### Для других платформ:
Сборку нужно выполнять на целевой платформе:
- **Windows**: Запустить pyinstaller на Windows → получится .exe
- **macOS**: Запустить pyinstaller на macOS → получится .app
- **Linux**: Запустить pyinstaller на Linux → получится исполняемый файл

### Команда для пересборки:
```bash
# Используя spec-файл (рекомендуется):
pyinstaller mp3tracker_v7.spec

# Или напрямую:
pyinstaller --onefile --windowed --name mp3tracker_v7 \
  --hidden-import=telethon \
  --hidden-import=telethon.tl.types \
  --hidden-import=mutagen.id3 \
  mp3tracker_v7.py
```

### Данные приложения:
Приложение хранит данные в `~/MP3_Tracker_Data/`:
- `tracked_mp3s.json` - отслеживаемые файлы
- `my_chats_v3.json` - список чатов
- `local_folders.json` - локальные папки
- `beat_packs.json` - пакеты битов
- `sent_packs.json` - отправленные пакеты
- `session/` - сессия Telegram

### Требования для запуска из исходников:
```bash
pip install customtkinter telethon pygame mutagen
python mp3tracker_v7.py
```

### Преимущества PyInstaller перед Electron:
✅ **Минимальные изменения кода** - приложение уже на CustomTkinter (нативный десктопный UI)
✅ **Меньший размер** - 46MB vs 150MB+ у Electron
✅ **Ниже потребление памяти** - нет необходимости запускать Chromium
✅ **Нативная производительность** - Python + SDL (pygame) работают быстрее
✅ **Простота поддержки** - один язык (Python), одна кодовая база
