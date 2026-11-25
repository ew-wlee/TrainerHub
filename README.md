<div align="center">
  <img src="src/trainerhub/resources/app_mark.svg" width="42" alt="TrainerHub logo">
  <h1>TrainerHub</h1>
  <p>A trainer manager for single-player games.</p>
  <p>Discover games · Download and organise · Open when you need them</p>
  <p><a href="https://github.com/ew-wlee/TrainerHub/releases/latest"><strong>Download for Windows</strong></a></p>
  <p>Windows 10 / 11 · No installer, account or Python required</p>
  <p>English · <a href="README.zh-CN.md">简体中文</a></p>
</div>

---

TrainerHub brings finding and organising game trainers into one window. Search by game name or scan your local Steam installation to find recommendations. Downloads are extracted and filed in your trainer library.

<img src="docs/images/readme/discover-en_US.png" alt="TrainerHub Discover page showing trainer recommendations for Steam games" width="100%">

> Screenshots use example data. Actual results and trainer availability depend on the source websites.

## Get started

1. Download `TrainerHub.exe` from [Releases](https://github.com/ew-wlee/TrainerHub/releases/latest) and open it.
2. Choose where to keep your trainers and which sources to use.
3. Search in Discover, or select **Scan Steam games** to see recommendations for games on your computer.
4. Choose a trainer and download it. Find it later under **My Trainers**.

The packaged app has no client dependencies to install. The default library is `%LOCALAPPDATA%\TrainerHub\Library`; you can change it in Settings.

## Find trainers for your games

### Start with your Steam library

Select **Scan Steam games** to read your local installation manifests and match installed games to available trainers. You can select several recommendations, rescan, or manage the games found by the scan.

The scan reads local installation information and does not modify game files. Recommendations match game names; **they do not establish compatibility with your current game version**. Check the source page before use.

### Search, inspect and download

Search the local catalogue by English or Chinese name, or pinyin. When you search, TrainerHub can also query FLiNG online. Select an entry to view the information available and start the download.

<img src="docs/images/readme/search-en_US.png" alt="An Elden Ring search result with its trainer details" width="100%">

Direct downloads are extracted and filed automatically. Entries distributed through external services open their source pages instead. Search and download availability can change when third-party websites change or go offline.

### Keep everything together

**My Trainers** shows downloads in progress and items already in your library. Search added trainers, open their folders, launch them, or confirm removal. You can also import a local folder.

<img src="docs/images/readme/library-en_US.png" alt="My Trainers showing download progress and actions for added trainers" width="100%">

Downloaded trainers never run automatically. They start only when you select **Launch trainer** or **Open**. **Removing an entry deletes its folder and files**, including an imported local folder, so check that you no longer need it first.

## Common questions

**What if I can't find a game?** Try its English or Chinese name, or an alias. Games that cannot be matched reliably by the Steam scan can still be searched manually; availability depends on third-party sources.

**How do I check version compatibility?** Search and recommendations help you find an entry, but do not verify compatibility with your current game version. Open the source page and check the supported versions.

**Is my Steam library uploaded?** Scanning and recommendations run locally and do not upload your game list in bulk. An online search may send your query and English aliases used for follow-up searches to FLiNG.

## Run from source

Install Python 3.12 and [uv](https://docs.astral.sh/uv/):

```bash
uv sync
uv run trainerhub
```

Run tests or build the Windows executable:

```bash
uv sync --extra dev
uv run pytest
uv run pyinstaller packaging/trainerhub.spec --noconfirm
```

## About the sources

TrainerHub indexes public information from third-party websites and manages downloads. It does not host, mirror or redistribute trainer files, is not affiliated with the sources or game publishers, and does not provide anti-cheat bypasses. Trainers are intended for offline single-player games; evaluate third-party executable files before running them.

The project is released under the [MIT license](LICENSE). See the [architecture notes](docs/architecture.md) for implementation details.
