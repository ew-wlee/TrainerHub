# TrainerHub

English · [简体中文](README.zh-CN.md)

TrainerHub is a Windows desktop tool for finding and organising trainers for single-player games. Search for a game or scan your local Steam library to see recommendations.

[Download the latest TrainerHub.exe](https://github.com/ew-wlee/TrainerHub/releases/latest)

## Using TrainerHub

1. Download and open `TrainerHub.exe`, then choose a library folder and sources.
2. Search in Discover or scan your installed Steam games. Searches support Chinese, English and pinyin; online searches send the query to FLiNG.
3. Download a trainer when a direct link is available. TrainerHub extracts and files it in your library; external downloads open the source page.
4. Use My Trainers to see download progress, search your library, open folders, run trainers or remove them.

Steam discovery reads local installation manifests. Recommendations match game names and do not establish version compatibility; check the supported version before using a trainer. Downloads are never run automatically.

The default library is `%LOCALAPPDATA%\TrainerHub\Library`. You can change it in Settings. The packaged app needs no account or Python installation.

## Run from source

Install Python 3.12 and [uv](https://docs.astral.sh/uv/):

```bash
uv sync
uv run trainerhub
```

Run tests and build the Windows executable:

```bash
uv sync --extra dev
uv run pytest
uv run pyinstaller packaging/trainerhub.spec --noconfirm
```

## Sources and license

TrainerHub indexes public information from third-party sites and manages downloads. It does not host, mirror or redistribute trainer files, is not affiliated with the sources or game publishers, and does not provide anti-cheat bypasses. Changes to source websites can affect search or downloads.

Trainers are intended for offline single-player games. Evaluate third-party executable files before running them. The project is released under the [MIT license](LICENSE); see the [architecture notes](docs/architecture.md) for implementation details.
