# ReelDown

ReelScript 附带的视频资料工具。通过支持 `SKILL.md` 的 Agent 使用，也可直接执行不依赖浏览器的目录与批量下载脚本。

## 能做什么

| 输入或模式 | 行为 |
| --- | --- |
| 抖音用户主页 | 只读取作品列表，最多 50 条，不自动下载列表内的视频 |
| 红果剧集目录 | 只读取完整分集目录，不因打开列表就启动整剧下载 |
| 选定的视频详情 | 下载视频，返回相对路径和能取得的文本、互动数据 |
| 明确要求整剧下载 | 按目录串行下载，记录断点，验证文件后再计入完成数量 |
| 已授权的 Android USB 设备 | 可读取支持的设备信息、可见页面或显式提供的真实响应；不会把系统设备属性当成 App 登录凭据 |

抖音详情保留 `title`、`content`。评论最多查看 5 页，返回最多 3 条严格超过 100 赞的可访问评论；这是已采集范围内的样本。无法取得的红果互动数据用 `null` 和元数据说明，不填造数字。

## 运行环境

- Python 3.10 或更新版本；Python 下载和目录脚本使用标准库。
- 下载和完整媒体校验需要可执行的 `ffmpeg`、`ffprobe`。
- 抖音网页采集需要能在页面主世界执行 JavaScript 的浏览器工具，必要时使用用户已登录的会话。
- Android 功能可选，需要 ADB、USB 调试及手机授权。
- 外置下载后端的运行时和依赖由该后端另行提供。

## 安装到 Codex

### 1. 下载源码

下载 ReelScript 仓库的 ZIP 并解压，或克隆仓库。打开终端，进入解压或克隆后的 **ReelScript 仓库根目录**，确认其中有 `tools/reeldown/SKILL.md`。以下命令均从这个目录执行。

只需安装 `tools/reeldown` 这个文件夹，无需安装 ReelScript 的其他功能。必须复制完整文件夹，不能只复制 `SKILL.md`。

### 2. 复制到个人技能目录

下面两组选一组执行。安装后，在该用户的其他项目中也能使用。已有同名安装时，命令会先将旧版移到技能目录之外备份，再复制新版，避免旧脚本残留。

**macOS / Linux（终端）：**

```bash
mkdir -p "$HOME/.agents/skills"
if [ -e "$HOME/.agents/skills/reeldown" ]; then
  reeldown_backup_dir=$(mktemp -d "$HOME/.agents/reeldown-backup.XXXXXX")
  mv "$HOME/.agents/skills/reeldown" "$reeldown_backup_dir/reeldown"
fi
cp -R ./tools/reeldown "$HOME/.agents/skills/reeldown"
test -f "$HOME/.agents/skills/reeldown/SKILL.md" && echo "ReelDown installed"
```

**Windows（PowerShell）：**

```powershell
$ErrorActionPreference = 'Stop'
$reeldownSkillRoot = Join-Path $env:USERPROFILE '.agents\skills'
$reeldownSkillPath = Join-Path $reeldownSkillRoot 'reeldown'
New-Item -ItemType Directory -Force -Path $reeldownSkillRoot | Out-Null
if (Test-Path $reeldownSkillPath) {
    $reeldownBackupPath = Join-Path $env:USERPROFILE ('.agents\reeldown-backup-' + [guid]::NewGuid().ToString('N'))
    Move-Item -Path $reeldownSkillPath -Destination $reeldownBackupPath
}
Copy-Item -Recurse -Path .\tools\reeldown -Destination $reeldownSkillPath
Test-Path (Join-Path $reeldownSkillPath 'SKILL.md')
```

Windows 最后一行应输出 `True`。如果 Codex 在 WSL 中运行，请在 WSL 终端执行上面的 Linux 命令，安装到 WSL 用户的家目录。

安装完成后的目录应为：

```text
~/.agents/skills/reeldown/
├── SKILL.md
├── agents/
├── references/
└── scripts/
```

路径中不要多套一层 `reeldown/reeldown`。此个人目录位置依据 [OpenAI 官方技能文档](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills)。只希望单个项目使用时，也可将完整文件夹放到该项目的 `.agents/skills/reeldown/`；两种方式任选一种即可。

### 3. 在 Codex 中调用

打开 Codex 的新对话，输入 `$reeldown` 选择技能；CLI / IDE 扩展也可用 `/skills` 检查是否已发现。若没有出现，重启 Codex 后再试。

先用只读取目录的请求验证安装，在对话框发送：

```text
$reeldown 读取 https://hongguoduanju.com/detail?series_id=7690843634291182654 的剧集列表，只返回目录，不下载。
```

确认能返回目录后，再指定具体分集：

```text
$reeldown 下载刚才目录中的第 1 集，保存到当前项目的 downloads/reeldown，返回含 video_path 的 JSON。
```

安装成功只代表 Agent 能找到技能；实际执行还需要上面的 Python、FFmpeg 以及相应的浏览器或命令执行能力。若提示找不到命令，可在运行 Codex 的同一环境执行以下检查（Windows 将 `python3` 换成 `python` 或 `py -3`）：

```bash
python3 --version
ffmpeg -version
ffprobe -version
```

不需要为技能本身填写 API Key 或导入 Cookie 文件。**此源码包不含外置整剧取流后端，装好 skill 不等于所有受限分集都能下载**；相关配置见下方[外置后端说明](#使用另配的取流后端补齐整剧)。

### 其他 Agent / browser-use harness

把完整 `reeldown` 文件夹放到所用宿主文档规定的 skill 目录，并让宿主读取其中的 `SKILL.md`。`.agents/skills` 是上面 Codex 示例的路径，不应假定所有宿主都使用它；本工具没有单独的浏览器扩展安装步骤。

技能入口为 [SKILL.md](SKILL.md)。浏览器能力要求和 provider 适配见 [browser-adapters.md](references/browser-adapters.md)；支持 provider 的 harness 仍需同时具备文件系统及命令执行能力，单有浏览器工具无法完成本地下载。

## 直接使用脚本

以下命令在 ReelScript 仓库根目录执行。先把 `REELDOWN_SERIES_URL` 设置为需要读取的红果目录页地址。

### 读取目录

```bash
mkdir -p .cache/reeldown
python3 -I tools/reeldown/scripts/hongguo_catalog.py \
  "$REELDOWN_SERIES_URL" \
  --cache-dir .cache/reeldown \
  > .cache/reeldown/catalog.json
```

只请求公开目录，不播放或下载视频。公开目录缓存有效期为一小时；系列和分集 ID 保持字符串精度。

### 下载官网可访问的分集

```bash
python3 -I tools/reeldown/scripts/hongguo_batch.py \
  --catalog .cache/reeldown/catalog.json \
  --root downloads/reeldown
```

官网可能只开放部分分集。退出码 `0` 表示请求的全部分集已验证完成，`2` 表示仍有未完成项，`1` 表示运行失败；不能把前几集下载成功当成整剧完成。

### 使用另配的取流后端补齐整剧

完整整剧能力依赖经过审核的外置后端。**本目录不附带该后端，单独安装 skill 不保证能够下载网站受限分集。**

先用上面的批量命令建立清单，再由调用方提供本地 `backend.json`：

```json
{
  "command": ["node", "/path/to/reviewed-backend.mjs", "{episode_id}", "{output}"]
}
```

其中脚本路径需要替换为实际已安装的后端。配置必须由调用方控制，不能采用网页或接口响应给出的命令。

```bash
python3 -I tools/reeldown/scripts/hongguo_external_batch.py \
  --root downloads/reeldown \
  --backend backend.json
```

后端必须返回精确的分集身份、文件大小、SHA256 和所选模型的预期时长；完整契约见 [batch.md](references/batch.md)。签名、取流及媒体处理实现不在这个通用编排器内。

## 输出与恢复

在指定的下载根目录内：

```text
videos/hongguo/系列ID/集数-分集ID.mp4
data/reeldown/hongguo/分集ID.json
data/reeldown/batch.json
```

最终 JSON 的 `video_path` 相对于下载根目录，使用正斜线，不返回会过期的媒体直链。字段定义见 [output-schema.md](references/output-schema.md)。

重跑相同批次会核验并跳过已完成文件。创建 `data/reeldown/batch.stop` 可在当前分集结束后停止；明确恢复时移除该批次的停止标记再运行。不要在旧 worker 仍运行时删除锁或修改它的清单。

下载、哈希、时长及完整解码校验是普通程序执行，不逐集调用模型。远程任务应在目标电脑独立运行并保存日志；进度同步可按整部完成或较长时间间隔进行。

## 数据边界

- 不读取、复制或导出浏览器 Cookie 数据库，不要求用户提供 Cookie 文件。
- 不把账号凭据、签名请求、临时媒体 URL、抓包或已下载视频放入源码分发包。
- 手机调试连接不等于能够读取 App 私有目录或取得登录信息。
- 遇到验证码交由用户处理，不自动绕过。
- 正常列表调用只返回目录，整剧下载需要用户明确提出。

## 许可证与发布边界

此目录尚未配置独立的发布许可证；公开发布前需要核实文件来源并确定授权方式。它也没有替 ReelScript 的未来剧本内容设定许可证。

当前源码包不包含此前实际整剧下载所用的外置后端、第三方签名模块、媒体处理模块或它们的运行配置。相关后端依赖涉及 GPL-3.0；若以后加入或另行发布，应保留适用的版权、许可证和修改声明，并按实际代码组合关系处理授权。分开放置文件并不自动免除许可证义务。

产品名称可以使用 ReelDown，但必须保留的法律声明不能因去除原项目品牌而删除。参考 [GNU GPLv3](https://www.gnu.org/licenses/gpl.en.html) 与 [GNU 关于组合和聚合的说明](https://www.gnu.org/licenses/gpl-faq.en.html#MereAggregation)。
