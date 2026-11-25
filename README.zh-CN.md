# TrainerHub 修改器管家

[English](README.md) · 简体中文

TrainerHub 是一个 Windows 桌面工具，帮助单机游戏玩家查找和管理修改器。你可以搜索游戏，也可以扫描本地 Steam 游戏，从推荐列表中选择需要的修改器。

[下载最新版 TrainerHub.exe](https://github.com/ew-wlee/TrainerHub/releases/latest)

## 使用

1. 下载并打开 `TrainerHub.exe`，首次运行时选择保存目录和数据源。
2. 在「发现」中搜索游戏，或扫描 Steam 游戏并查看推荐。搜索支持中文、英文和拼音；联网搜索向风灵月影发送查询词。
3. 下载支持直链的修改器。程序会解压并归档文件；需要网盘下载的条目会打开来源页面。
4. 在「我的修改器」中查看下载进度，搜索已归档的修改器，或打开目录、运行和删除。

Steam 扫描只读取本机安装清单。推荐依据游戏名称匹配，并不保证修改器与当前游戏版本兼容，请在使用前自行核对。下载的程序不会自动运行。

默认库目录位于 `%LOCALAPPDATA%\TrainerHub\Library`，可以在设置中更改。程序不需要账号或本机 Python 环境。

## 从源码运行

需要 Python 3.12 和 [uv](https://docs.astral.sh/uv/)：

```bash
uv sync
uv run trainerhub
```

运行测试并构建 Windows 程序：

```bash
uv sync --extra dev
uv run pytest
uv run pyinstaller packaging/trainerhub.spec --noconfirm
```

## 数据来源与许可

TrainerHub 索引第三方网站公开的信息并调度下载，不托管、镜像或再分发修改器文件。项目与风灵月影、小幸修改器及游戏发行商没有关联，也不提供反作弊绕过功能。第三方网站变更可能影响搜索或下载。

修改器面向单机离线游戏；使用第三方可执行文件前请自行判断风险。项目以 [MIT 许可](LICENSE)发布，技术设计见 [架构说明](docs/architecture.md)。
