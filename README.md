<div align="center">

<img src="src/trainerhub/resources/app_mark.svg" width="40" alt="" />

# TrainerHub

**English** | [简体中文](README.zh-CN.md)

Find a trainer. Install it. Go play.

A small Windows tool for single-player game trainers — search, download, unpack, done.

[![Release](https://img.shields.io/github/v/release/ew-wlee/TrainerHub?color=191817&label=release)](https://github.com/ew-wlee/TrainerHub/releases/latest)
[![License: MIT](https://img.shields.io/badge/license-MIT-2E6B4E.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-191817.svg)](#install)

### [Download TrainerHub.exe](https://github.com/ew-wlee/TrainerHub/releases/latest)

60 MB · no installer · no account · no Python

</div>

<img src="docs/screenshots/01-discover.png" alt="TrainerHub — search, pick a game, download the trainer" width="100%" />

## What it does

- **Search once.** FLiNG and 小幸修改器 in one list, by Chinese name, English name, full pinyin or initials.
- **One click to install.** Streams the file, verifies it, unpacks it, and files it under the game's name.
- **A library you can find.** Every installed trainer listed by game — open the folder, run it, or delete it.

## Install

Download `TrainerHub.exe` above and double-click it. Windows 10 or 11, nothing else to install.

The library lives in `%USERPROFILE%\TrainerHub\Library` by default; change it in Settings.

## Run from source

```bash
# Python 3.12+ and uv
uv sync
uv run trainerhub
```

Build the executable:

```bash
uv sync --extra dev
uv run pyinstaller packaging/trainerhub.spec --noconfirm
# → dist/TrainerHub.exe
```

## Notes

Trainers are for single-player, offline use. Running one in an online session can get your
account banned.

TrainerHub indexes what the sources publish and schedules the download. It does not bundle,
mirror or redistribute any trainer binary, does not provide anti-cheat bypasses, and is not
affiliated with FLiNG, 小幸修改器 or any game publisher.

MIT licensed. The architecture notes live in [`docs/architecture.md`](docs/architecture.md).
