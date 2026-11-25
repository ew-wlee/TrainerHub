# 架构说明

## 分层

```
ui/         PySide6 视图与交互（无业务逻辑）
workers/    QThread 桥接：同步、详情、下载、联网搜索、Steam 发现
core/       纯 Python 业务层（可单测、可被 CLI 复用）
```

依赖方向单向向下：`ui → workers → core`。`core` 不 import Qt，`workers` 只做线程封装。

## 数据流

```
UI 事件
  └─ worker.enqueue(item)
       └─ core.Source.fetch_detail()  →  core.Database.save_detail()
       └─ core.Source.resolve_download()
       └─ core.Downloader.fetch()     →  .part 流式写入 → 原子改名
       └─ core.archive.extract()      →  临时目录 + 路径校验
       └─ core.Library.install()      →  library/source/game/version/ + manifest.json
  ← Signal(item / progress / installed)
```

所有跨线程通信都通过 Qt 信号；worker 内部用 `threading.Event` 做协作式取消。

## 两阶段同步

| 阶段 | 触发 | 请求量 | 落库字段 |
| --- | --- | --- | --- |
| 列表 | 启动/手动同步 | 每源约 1–8 次（`per_page=100`） | 标题、游戏名、别名、版本、链接、更新时间 |
| 详情 | 选中条目时懒加载 | 每条 2 次（REST content + 详情页 HTML） | 修改项、支持的游戏版本、文件大小、封面、真实版本 |

理由：详情页只有走到具体条目时才需要，全量预抓 800 条会产生 1600 次请求，
既慢又容易被限流。

## 搜索

不使用 FTS5：条目量级只有数千，启动时把整表读进内存构建归一化索引更快，也避免了
不同平台 SQLite 编译选项不一致的问题。

匹配顺序（命中即停）：

1. 归一化后的游戏名完全相等（1000）
2. 游戏名前缀（900）
3. 游戏名包含（780）
4. 别名包含（720）
5. 全拼前缀 / 包含（560 / 480）
6. 拼音首字母前缀 / 包含（520 / 440）
7. 原始标题包含（380）

命中数不足 8 条时补一轮 `rapidfuzz.WRatio`（阈值 62）兜底拼写错误。
排序键：`(score, updated_at)`。

## Steam 发现与联网来源裁决

- `core/steam_scan.py`：受限 VDF 解析，只读多库安装清单，取消不提交半成品。
- `core/game_matching.py`：预计算游戏名／可靠别名，保护续作、版本及 DLC 身份；搜索排序分数不等于推荐置信度。
- `core/source_policy.py`：先游戏级合并与 FLiNG 优先，再应用来源筛选；网络失败不冒充没有 FLiNG。
- `core/recommendation.py`：本地快照和目录生成高、中置信计划，不联网、不执行；已有项不重复选择。
- `workers/discovery_worker.py`：在后台扫描与生成计划；`ui/discovery_controller.py` 接收有效代次后事务提交快照，维护选择与任务状态。
- `workers/search_worker.py`：有限英文别名补搜，返回查询代次与来源；旧回包不能覆盖当前查询。外站链接和响应类型在 `core/remote_search.py` 校验。
- 隐私、扫描诊断与推荐依据在设置／次级详情；首屏只显示必要信息。清除或关闭先取消并失效代次，不删除修改器库。

## 下载管道状态机

```
queued → resolving → downloading → extracting → installing → done
              ↘ failed / cancelled / external
```

- **resolving**：需要时先补详情，再解析出真实 URL；若来源只提供网盘，走 `external`。
- **downloading**：写 `.part`，按 Content-Length 报进度，取消即删临时文件。
- **extracting**：按魔数判断容器；zip 用 `zipfile`，7z 用 `py7zr`，裸 exe 直接进入归档。
- **installing**：移动到 `library/<source>/<game>/<version>/`，写 `manifest.json`，更新 SQLite。

去重键 `(source_id, remote_id)` + 版本比较：同版本重复下载直接跳到"已在库"。

## 安全边界

| 风险 | 处理 |
| --- | --- |
| Zip Slip | 解压前逐条校验成员路径，拒绝绝对路径、盘符、`..` |
| 解压炸弹 | 限制文件数与解压后总体积 |
| 自动执行 | 任何下载物都不会被程序自动运行 |
| 任意文件删除 | 删除操作限定在库记录对应的目录内 |
| Defender 排除项 | 仅 Windows、仅库目录、二次确认、明确提示需要管理员权限 |

## 存储

- **SQLite**（`catalog` / `installed` / `meta` / `steam_games` / `steam_preferences`）：目录、修改器库、Steam 快照与排除偏好，WAL 模式。发现表独立建表，不改变旧主键；只替换成功扫描的库，不把不可访问外置库当作卸载。
- **JSON 配置**：主题、语言、库目录、源开关、下载并发等，原子写入（临时文件 + `os.replace`）。
- **manifest.json**：随每个已安装版本落盘，脱离程序也能读懂来源。

## 为什么是 PySide6 而不是 PyQt6

PyQt6 采用 GPL-3.0，与本项目的 MIT 许可不兼容（分发时会传染）。PySide6 是 LGPL，
可以在 MIT 项目中分发。两者 API 高度相似，迁移成本低。

## 如何新增一个数据源

1. 在 `core/sources/` 新建适配器，继承 `BaseSource`；
2. 实现 `fetch_page`（必需）、`fetch_detail`（可选）、`resolve_download`（可选）；
3. 声明 `supports_direct_download` 与 `requires_detail` 两个能力标记；
4. 在 `core/sources/base.py::build_sources` 注册；
5. 用本地 fixture 补一条离线单测（参考 `tests/test_sources.py`）。

UI 不需要任何改动——按钮文案由能力标记驱动。
