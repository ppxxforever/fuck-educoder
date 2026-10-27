# Educoder 作业提醒工具

Python + uv + Playwright。支持本人进行中课堂、两类作业采集、SQLite 保存和 Server 酱推送。
Server 酱³ 接收端为独立 App；Turbo 可配置微信通道，程序根据 SendKey 前缀选择接口。

## 使用

```bash
uv sync --locked
# 新环境将 .env.example 复制为 .env，填写认证字段，并 chmod 600 .env
uv run python -m educoder_reminder.courses
# 重新发现本人课堂，采集两类作业并更新数据库
uv run python -m educoder_reminder.homeworks
uv run python -m unittest discover -s tests
```

想一次看到全部状态并直接跑命令，用控制台 TUI（Textual，见下节）：

```bash
uv run python -m educoder_reminder.tui          # 启动界面
uv run python -m educoder_reminder.tui --dump   # 只打印本地状态摘要（无界面、不联网）
```

日常采集使用 Playwright APIRequestContext 直接请求课堂接口；仅自动恢复登录时启动 Chromium。
只访问配置的本人课堂接口，固定 status=processing，遍历分页并再次排除 is_end=true。
结果保存为 data/courses.json，包括 ID、名称、课堂标识、链接和可访问状态。
认证失败、响应结构异常、重复分页或分页不完整时退出，保留上一次完整结果。
每次采集前调用 `/api/users/get_user_info.json?school=1` 获取当前登录用户的 `login`，
据此生成个人课堂地址和课堂接口参数。无需手工填写账号标识或课堂地址。
`EDUCODER_CLASSROOMS_URL` 仅作为自动维护的账号缓存：旧值与会话不一致时，会通过
账号密码重新登录，以新登录返回的 `login` 更新缓存；不会继续使用旧账号地址。

## 控制台 TUI

`educoder_reminder/tui/` 是 Textual 版总控制台，把分散的子命令收拢到一个界面里。
界面只读本地数据（`data/`、`.env`），刷新不会触发网络请求；所有联网 / 提交 / 推送
都通过子进程调用现有 CLI，界面进程本身不启动 Playwright。

```bash
uv run python -m educoder_reminder.tui
```

界面不使用按钮控件：每页底部是一行 `[按键] 动作` 操作条，可以直接鼠标点击，
也可以按对应按键；`1`–`5` 或点击标题切换分页，`Ctrl+Q` 退出，`F1` 查看帮助，
建议终端至少 110×30。

| 分页 | 内容与操作条 |
|------|--------------|
| 概览 | 当前账号 / Token·Cookie / AI / 推送 / 登录冷却、作业与提醒统计、队列概况、最近待办（回车跳到作业清单）<br>`[r]` 刷新 `[c]` 同步课堂 `[h]` 同步作业 `[p]` 提醒预览 `[k]` 校验配置 `[a]` 认证检查<br>`[P]` 爬题预览 `[G]` 预生成答案 |
| 课堂·作业 | 本地数据库里的作业清单，可按名称搜索、按状态和类型筛选<br>`[/]` 搜索 `[o]` 打开选中作业 `[r]` 刷新 |
| 多账号队列 | 账号增删改、手动设置状态、当前账号、验证密码，**每个账号单独选课程**<br>`[u]` 设为当前 `[v]` 验证密码 `[i]` 修改信息 `[t]` 设置状态 `[m]` 显示密码 `[d]` 删除<br>`[g]` 选择课程 `[s]` 提交选中账号 `[b]` 全部开始提交 `[e]` 保存到队列 |
| 执行任务 | 选择现成命令（采集、提醒、提交、题库预生成、队列、修复未记通关）→ 填参数 → 运行，日志实时滚动<br>`[n]` 禁用 AI `[l]` 先释放环境 pod `[F5]` 运行 `[x]`/`Ctrl+S` 停止<br>`[P]` 爬题预览 `[G]` 预生成答案（跳到题库任务并运行，复用上面的课堂/limit/实验参数） |
| 实时日志 | 跟踪 `data/queue.log` 与 `data/tui.log`<br>`[r]` 刷新 `[f]` 跟随最新 `[y]` 清空视图 |

### 按账号指定课程

队列页选中账号后按 `[g]` 打开课堂多选：空格 / 回车切换，`a` 全选，`n` 清空，`s` 保存
（不选 = 该账号处理全部课堂）。选择结果写入 `data/accounts.json` 的 `classrooms` 字段：

```json
{"account": "13800000000", "password": "xxx", "note": "同学A",
 "classrooms": ["2i6ng7vp", "数据库原理"]}
```

右侧「添加 / 更新账号」表单也能直接填课程 code/名称（逗号分隔）。更新已有账号时
表单课程留空会**保留**原有设置；要清空请用 `[g]` 里按 `n` 再保存。

### 修改账号信息

选中账号按 `[i] 修改信息`：表单会载入该账号、密码、备注和课程，账号本身也可以改名
（队列状态会一起迁移）。改完按 `[e] 保存修改`，按 `[esc]` 或点 `[esc] 取消编辑` 放弃。
密码留空表示保留原密码；加密密码无法解密时也会提示留空保存。

### 手动设置状态

选中账号按 `[t] 设置状态`：

- `[p] 待处理`：重新进入队列；
- `[d] 已完成`：`run_queue` 默认跳过该账号；
- `[f] 失败`：记录为“手动标记失败”；
- `[z] 清空进度`：状态改为待处理，同时把提交/失败/跳过计数清零。

只修改本地 `data/queue_state.json`（`manual` 字段标记为手动设置），不改变平台作业状态；
下次真实运行该账号时会写回新的运行结果。

### 提交：单个账号或全部

- `[s] 提交选中账号`：只跑队列里选中的账号，使用该账号自己的课程设置。
  确认框里的命令会显式带上课程，例如：
  `run_queue.py --apply --only 138xxx --force --classroom 2i6ng7vp --classroom 数据库`
- `[b] 全部开始提交`：按队列顺序串行提交所有账号，每个账号用自己的课程设置，
  已完成的账号会跳过（要强制重跑用 `[s]`）。一条命令无法表达每个账号不同的课程，
  所以不带 `--classroom`；`run_queue.py` 会在日志开头打印「课程安排」，
  并在每个账号开始时再打印一次实际使用的课程；
- 两者都会弹确认框，显示账号与课程；`limit` / `poll-timeout` / 账号间隔 / 禁用 AI
  取自「执行任务」页。

其他要点：

- 「执行任务」页的课堂筛选是**全局覆盖**；队列页的两个提交动作不使用它，按账号自己的设置；
- 不相关的输入框会按任务自动禁用，确认框会显示将要执行的完整命令；
- TUI 里跑过的任务会同时追加到 `data/tui.log`，退出后仍可在「实时日志」查看；
- 后台 systemd 服务运行时，真实提交/推送会与它共用登录会话与进程锁，
  建议先 `sudo systemctl stop educoder-reminder` 再在 TUI 里提交；
- 需要一个极简、只依赖标准库的队列界面时，仍可用 `scripts/tui.py`（curses，仅多账号队列）。

## 作业采集

每次运行先刷新本人进行中课堂清单，随后仅访问清单内课堂的
`/api/courses/{课堂标识}/homework_commons.json`。
`type=4` 为课堂实验，`type=1` 为图文作业；`status=0` 保留全部可见状态，
从而在后续同步时检测已逾期作业的延期。分页使用 `page`、`limit` 和
`query_total_count`，不使用包含未发布作业的 `all_count`。

- 截止日期优先读取精确的 `end_time_s`，缺失时读取 `end_time`，按北京时间保存。
  不将补交时间 `late_time` 当作正常截止日期。
- 实验使用 `shixun_finished_status` 判断完成；图文作业使用 `un_commit_work`
  判断是否提交。无法识别的状态单独标注，不推断为未完成。
- 列表中遇到 `is_archive=true` 立即跳过，仅计入分页数量，不解析作业内容、
  不写入本次数据库快照或 JSON，不请求归档详情。实测接口“已截止”筛选仍包含归档项，
  因此列表响应可能附带归档记录；尚未验证到可用的服务端排除参数。
- 已完成、未发布和逾期作业不进入待提醒列表；无截止日期的未完成作业
  标记为 `no_deadline`，供后续单独提醒。
- 截止时间距本次同步开始已超过 5 天（120 小时）的作业，在读取截止时间后立即跳过，
  不解析其余内容、不写入本次结果；恰好 5 天仍保留。旧数据库记录标记为非当前项。
  接口列表仍可能附带这些记录；按本次返回的新截止时间判断，老师延期后可以重新纳入。
- 保留历史记录；本次清单中消失的课堂/作业标记为 `present=0`，不继续提醒。
  采集失败不会将旧记录标记为消失。数据库写入使用事务。

输出：

- `data/reminder.sqlite3`：`homeworks` 存储作业及当前状态，`deadline_changes`
  记录已知作业截止日期的修改；延期后的未完成作业可重新成为待提醒项。
- `data/homeworks.json`：本次完整结果、北京时间同步时间和分类统计，方便人工核对。
  `pending` 表示尚未截止且未完成，并不表示现在就需要发送 24 小时/1 小时提醒。
  JSON 中的分类是同步时刻快照，未来提醒任务须按当时的时间重新计算。
- 作业链接指向对应课堂的作业列表。当前不会打开实验、提交作品或修改任何作业。

## 认证

认证字段仅放在本地 .env 中，不提交 Git。每次请求根据当前毫秒时间自动生成签名，
实现依据官网公开客户端 setHeader/getKey 逻辑，并使用真实浏览器请求作为测试向量。
不再需要配置固定 Timestamp 或 Signature。服务器须保持系统时间同步；网站变更签名
算法可能需要更新代码。Cookie/Token 过期不等于签名过期；支持通过正常的账号密码表单
自动恢复会话。认证失败不会当作零课堂。

在服务器本地 `.env` 填写（不要在命令行参数或日志里放密码）：

```dotenv
EDUCODER_LOGIN_ACCOUNT='你的手机号、邮箱或登录账号'
EDUCODER_LOGIN_PASSWORD='你的密码'
```

登录账号可以是手机号/邮箱；`EDUCODER_CLASSROOMS_URL` 可以留空，由程序自动生成。
Token/Cookie 可以保留；不再有效时自动恢复。也支持只有账号密码的首次登录。
按字面读取密码，密码中的 `$` 不会被当作环境变量替换。

以实际运行服务的普通用户安装浏览器，系统依赖通过 sudo 安装：

```bash
uv run playwright install chromium
sudo .venv/bin/python -m playwright install-deps chromium
# 联网校验身份，失效时自动登录；不会发送推送
./scripts/run.sh auth-check
```

后台服务已运行时，先 `sudo systemctl stop educoder-reminder` 再手动执行 `auth-check`，
完成后 `sudo systemctl start educoder-reminder`。普通 `check` 仍仅检查配置。

自动恢复流程：确认未登录 → 无界面浏览器填写账号密码并选择“下次自动登录” →
提取会话 → 调用身份接口取得 `login` → 原子更新 `.env` 中的 Cookie、Token 和课堂地址 →
同账号重试原请求一次。若采集中途登录为新账号，则停止旧批次，下次从新账号的课堂
列表开始，避免复用旧课堂请求。数据库和提醒记录始终按实际登录账号隔离。
凭据保存权限为 `600`；服务用户须对 `.env` 及项目目录有写权限。
后续采集复用新凭据，浏览器随登录流程结束关闭。

密码提交每 30 分钟最多一次，滚动 24 小时最多 3 次；记录存入 `data/auth.sqlite3`，
重启服务不会清除限制。网络错误、签名错误或普通权限不足不会直接触发密码登录。
如果网站增加验证码/短信验证，程序会报错等待处理，不会绕过验证。
登录失败或保存失败不会覆盖原有凭据；重新登录成功则以身份接口结果更新缓存。
目前认证异常记录在服务日志中，尚未增加专门的 App 登录失效告警。

## 根据 answers.json 自动提交作业

`educoder_reminder.submit` 读取项目根目录的 `answers.json`（class-answers 格式），
按课堂/实验/关卡逐个把答案提交到头歌：选择题回填并提交，代码题写入远程工作区并触发评测。
复用上面的 `.env` 认证（账号密码或 Cookie/Token 均可，失效时自动恢复）。

```bash
# 预览：只读平台当前状态，打印每个关卡会提交什么、跳过哪些，不真正提交
uv run python -m educoder_reminder.submit

# 确认无误后真实提交
uv run python -m educoder_reminder.submit --apply

# 只处理某个课堂 / 只跑前 N 个关卡（测试用）/ 调评测等待秒数
uv run python -m educoder_reminder.submit --classroom 2i6ng7vp
uv run python -m educoder_reminder.submit --limit 3 --apply
uv run python -m educoder_reminder.submit --apply --poll-timeout 120
```

安全策略：跳过 `answered=false` 或无答案的关卡、平台已通过（`game.status==2`）的关卡、
已标记完成（`shixun_finished_status==1`）的实验，以及**已截止 / 已归档的实验**
（按 `end_time_s`（优先）或 `end_time` 判断）。确需补交时加 `--include-expired`；
代码题只处理单文件关卡，多文件关卡跳过以免半提交。
选择题先按 answers.json 直接提交，若格式导致未全对，会用平台在提交响应里回吐的标准答案键兜底重交一次；
代码题评测默认等待 90 秒，超时或未通过请在平台确认。


### UML/图形化绘图题自动提交

`educoder_reminder.submit_uml` 处理画 UML 图（StarUML `.mdj`）的图形化实验：
SSH 登录 VNC 虚拟机 → 写入工作区 → `git commit` → 触发评测。

答案来源优先级：
1. 本地题库 `answer/<实验名>/`（`.mdj` 或 `stepN/res.txt`）；
2. 缓存/抓取的评测脚本逆向构造（`graders/`，按 gid 与「关卡标题+step」双键缓存，
   换账号或换机器都能命中；该目录随仓库提交）；
3. AI 生成（需配置 `AI_API_KEY`）。

```bash
uv run python -m educoder_reminder.submit_uml            # 预览
uv run python -m educoder_reminder.submit_uml --apply    # 真实提交
uv run python -m educoder_reminder.submit_uml --apply --experiment "面向对象分析之用例图"
uv run python -m educoder_reminder.submit_uml --apply --release-envs   # 清理环境 pod
```

注意：每个图形化实验占用一个 VNC 环境，平台对并发数有上限（实测约 5 个）。
遇到「用户创建实验环境数已达上限」时程序会**自动释放本课堂已打开的环境 pod 并重试一次**
（等待 5 秒）；仍失败则提示稍后再试。也可手动先清理：

```bash
uv run python -m educoder_reminder.submit_uml --release-envs
```

每个实验结束默认也会自动释放它的环境（`--no-release` 可关闭）。

### 一键提交

```bash
uv run python -m educoder_reminder.submit_all            # 预览
uv run python -m educoder_reminder.submit_all --apply    # 真实提交
```

平台驱动：检测本人进行中的课堂（`created_at` 早于 `COURSE_CUTOFF` 的旧学期课堂会跳过）
→ 拉实验列表 → **跳过已截止/已归档实验**（`--include-expired` 可强制处理）
→ 与平台实时核对已通过状态 → 对未通过关卡分派到选择/代码题与 UML 题流程。

### 评测通过但平台仍显示「未通关」

官网提交代码的流程是：`update_file.json` 带 `evaluate=1` 保存 → 用响应里的 `sec_key`
调用 `game_build.json` 触发评测。旧版本用空 `sec_key` 提交，平台仍会评测并给分，
但经常不把该关卡写成 `status=2`，页面上就一直显示「未通关」。

现在已按官网流程修正（`evaluate=1` + `sec_key` + `resubmit`/`content_modified`），
并把评测轮询改到官网前端使用的 `/api/tasks/{gid}/game_status.json`。

历史上已经变成「有分数但 status=0」的关卡不会自动重交（工具把它们当作已通过，
避免每次运行都重复提交）。需要修正时执行一次：

```bash
uv run python -m educoder_reminder.submit_all --apply --repair-status
uv run python -m educoder_reminder.submit_all --apply --repair-status --classroom 2i6ng7vp
uv run python scripts/run_queue.py --apply --repair-status
```

`--repair-status` 只重交「测试已通过、但 `game.status != 2`」且有本地答案的关卡。
TUI 的「执行任务」页也有同名任务；先不加 `--apply` 可以预览。

#### 「评测通过 ✔」之后还会再确认一次通关

`wait_for_verdict()` 认可两种「评测通过」信号（`status==2` / `test_sets` 全过），
但平台只把 `game.status==2` 当「已通关」。两者不一致时旧版本只打
一行「评测通过 ✔」，看起来像已经稳了。现在：

1. **sec_key 缺了就重试**：`update_file` 响应没带 key 时先连续问 `game_status.json`，
   再不行就重跑一次 `update_file(evaluate=1)`，仍拿不到则打印
   `⚠ 拿不到 sec_key，平台可能只评分不记通关`。
2. **通过后等通关**：`wait_for_completion()` 轮询详情等 `status==2`
   （宽限秒数 `EVAL_CONFIRM_TIMEOUT`，默认 20，设 0 可关闭）。
   等不到就打印
   `⚠ 评测通过，但平台未把关卡记为已通关（status≠2）；下一轮会重交，也可以稍后用 --repair-status 重修`，
   并计入汇总里的 `unconfirmed`。
3. **平台进度对账**：每个课堂跑完再拉一次作业列表，若本轮动过的实验仍是
   `shixun_finished_status != 1`，打印 `⚠ 平台仍显示未完成：<实验>` 并计入
   `stale_homework`。`scripts/run_queue.py` 会把这两个计数写进 `queue_state.json`，
   `scripts/queue_status.py` 在账号状态里直接显示。

这两类告警不影响「账号本轮完成」的判定（历史行为：有分数没 status 的关卡不重复重交，
避免把提交次数烧在平台同步问题上），但不会再静默。

> 2026-10-26 修正：判定口径里删掉了 `final_score>0`。`final_score` 是关卡分值，
> 不是通关信号——「绘制销售额饼图」当时 `status=0`、`final_score=100`、
> 唯一测试集 `result=false`（图像对比不一致），旧口径把它当成已通过，
> 之后每轮都「[跳过] 已通过」，平台永远停在未通关。
> 图像对比类（Matplotlib）关卡的 `solutions/` 也只收 `status==2` 确认过的答案。

> 2026-10-26 修正（第二个根因）：`game_build` 以前没带官网前端的顶层字段
> `homework_common_id`（`update_file` 的 extras 也少了 `smart_plan_page_item_bank_id`）。
> 少了它，平台照样评测、照样给分、`test_sets` 也显示通过，但**不把
> `game.status` 写成 2**——这就是「评测通过 ✔ / 测试集全过，平台却仍显示未完成」
> 的直接原因。现在两个请求的 payload 已与浏览器实测抓包对齐。

#### 图像对比关卡的排查方法

Matplotlib 这类关卡是像素级比图（`图像对比不一致，请检查你的代码`），
测试脚本本身读不到，但平台会把**标准图**和**你生成的图**都放在页面上：

```text
GET /api/tasks/<gid>/picture_display.json[?homework_common_id=<hw>]
  -> {"answer_picture": [{"pic_url": "..."}], "user_picture": [{"pic_url": "..."}]}
GET https://data.educoder.net< pic_url >   # 带登录 Cookie 下载 PNG
```

把两张 640×480 的 PNG 做像素 diff，就能直接量出差异：标题字号、
柱宽、`explode`、图例文字、坐标轴标签字号，一次就能对齐。
2026-10-26 用这个方法把本课程 11 个 Matplotlib 关卡全部修到 `status==2`
（其中「简单柱状图」「并列柱状图」「单/多折线图」的标准图是 matplotlib 3.7
渲染的，平台是 3.1.1，文字基线差 1~2px，答案里按像素对齐了）。

### 实验收尾校验（防「关卡被静默漏掉」）

选择/代码题链（`submit.py`）和图形题链（`submit_uml.py`）各自遍历关卡链，
任何一方遇到「不归我管」的关卡都会让出去。2026-10-25 就踩到过：图形化实验里的
选择题关卡（`软件详细设计-2` 的 McCabe方法/Halstead方法、`面向数据流的设计方法-2`
的事务型结构图）两边都没认领，图形题全部「评测通过」、选择题一题没交，
实验在平台上永远是「未提交」，而整轮运行退出码还是 0。

现在这条路径被堵死了，共三层：

1. **统一题型判定**：`educoder_reminder/levels.py` 的 `classify_level()` 是全项目唯一口径
   （choice / code / graphic / unknown），先看 `answers.json` 记录的题型，
   再看 `chooses`，最后才看环境/路径。带 VNC 环境的选择题不会再被当成绘图题。
2. **无主关卡必须上报**：两条链都会把「我处理了什么」写进 `levels.Coverage`；
   判不出题型的关卡不再 `continue` 静默跳过，而是打印 `✗ [无主关卡]` 并计入 `unowned`。
3. **实验收尾校验**：每个实验跑完，`submit_all` 会独立从入口关卡重新走一遍关卡链
   （不依赖上面两条链的遍历结果），把「未通关」的关卡全部列出来；
   入口只解析一次，三条链共用（平台换尝试时 gid 会整体换新，各解析一次会出现
   「提交打在旧链、审计看新链」）；「详情读不全」不算未通关，而是计入
   `audit_error`，下一轮重查：

```text
✗ 实验收尾校验：软件详细设计-2 仍未完成，还剩 1 关
    · 事务型结构图（choice，submit，attempted）
```

后果是硬性的，不会再「看起来成功」：

- 未完成明细写入 `data/unfinished.json`，TUI 概览页会显示「上次校验 N 个实验 / M 关未完成」；
- 有未通关关卡 / 无主关卡 / 无法校验时，`submit_all` 退出码为 1，
  队列里该账号状态置为 `pending`（下一轮自动重试，不会被 `--skip-done` 跳过）；
- `uv run python scripts/queue_status.py` 会直接列出未完成关卡数。

预览（不加 `--apply`）时同样会跑收尾校验，只是把「待提交」当成预览信息，不计入失败；
但「无主关卡」在任何模式下都算错误。

对应的回归测试在 `tests/test_levels.py`（题型判定、Coverage、审计、run_all 报告落盘）。

### 关卡详情残缺时不再「判不出题型」（2026-10-26 紧耦合&高内聚）

平台换了一轮尝试（同一个「内聚和耦合」的 gid 实测从 `cbymif92phj4` →
`fjavozk5ml7t` → `l9i3eofnfmpc`）之后，第一次 `GET /api/tasks/{gid}.json`
常常只回 `game` + 精简 `challenge`：没有 `subject`、没有 `chooses`、没有 `path`，
几秒后才补全。旧版本直接拿这份残缺详情去匹配标题，结果这一关被判成
`unknown`、记成「无主关卡」，而本地 `answers.json` / `solutions/` 里明明存着答案：

```text
✗ [无主关卡] ：题型无法判定（没有选择题/代码题线索，也不像图形题），本次未处理；请人工确认。
✗ 实验收尾校验：紧耦合&高内聚 仍未完成，还剩 1 关
    · 内聚和耦合（unknown，无人负责（工具漏处理），unknown）
```

现在改成四层兜底：

1. `submit.detail_of()`：详情里没有任何线索时重读几次（默认 3 × 1.5s），
   拿到带 `subject`/`chooses` 的完整详情再往下走；`submit_uml` 也用同一入口。
2. `levels.recorded_kind()`：`answers.json` 记过的题型优先，`uml` 也折成 `graphic`，
   不再让残缺详情猜出来的题型把答案交错关卡。
3. `levels.match_unlabelled_level()`：若平台始终不给标题，且关卡链长度 == 本地记录数，
   就按关卡顺序配对本地答案；数量对不上宁可报 `unknown`，也不乱配。
4. `submit_choice_game()`：拿不到 `chooses` 时直接报错跳过，绝不提交空答案。

### 未通过关卡存档（attempts/）

代码题 / UML 题评测未通过（含评测启动失败、平台未记通关）时，会自动把本次答案和平台反馈
按「实验 → 关卡」存到：

```
attempts/<实验名>/<关卡标题>/
    answer.py|.sql|.java|.c|...   # UML/图形题是 answer.mdj；选择题是 answer.json
    feedback.txt                  # 平台返回的编译/测试输出
    meta.json                     # 课堂、gid、远端路径、时间、是否已通过
```

复用规则：

- 普通运行：`answers.json` 没有该关卡答案时，代码题优先读 `attempts/.../answer.*`；
  UML 在 `answer/`、`submit_*/` 都找不到 `.mdj` 时也会读 `attempts/.../answer.mdj`；
- `--repair-status`：优先用 `attempts/` 里的存档重交，适合「改完 answer.* 再重跑」；
- 提交通过后 `meta.json` 的 `passed` 变成 `true`，之后不再自动复用（文件保留作参考）；
- 想放弃存档、让工具重新用 AI 生成，删除对应的关卡文件夹即可；
- 少数图形关卡平台没有返回保存路径（`challenge.path` 为空），工具默认跳过。
  如果确实要提交，在对应关卡文件夹里新建 `target.txt`（写工作区相对路径，
  如 `程序流程图/submit/step_4/step4.mdj`）或在 `meta.json` 的 `path` 里填写，
  再用 `--repair-status` 重交。

已有的未通过关卡可以一次性只读归档（不提交、不改平台数据）：

```bash
# 只列出未通过 / 未记通关的关卡
uv run python scripts/archive_failures.py --no-archive --classroom 2i6ng7vp

# 归档：本地有答案就存本地答案；缺答案的图形题可用 AI 生成一份初始 .mdj
uv run python scripts/archive_failures.py --classroom HCEAP94S --classroom 2i6ng7vp
uv run python scripts/archive_failures.py --classroom 2i6ng7vp --generate-missing
```

TUI 的「执行任务」页也有「采集 · 归档未通过关卡」。

### 已完成答案库（solutions/）

平台确认已通关（`game.status == 2`）后，答案会另外存一份到：

```
solutions/<实验名>/<关卡标题>/
    answer.py|.sql|.java|.mdj|.json
    meta.json   # 课堂、gid、远端路径、来源、完成时间
```

- 与 `attempts/` 分开：`attempts/` 只留未通过的尝试，`solutions/` 只放已通关答案；
- 代码 / UML / 选择题提交通过后都会自动写入；
- 历史已完成关卡可一次性归档（只读，不提交）：

```bash
uv run python scripts/archive_solutions.py --classroom 2i6ng7vp
uv run python scripts/archive_solutions.py --classroom HCEAP94S --classroom 2i6ng7vp
uv run python scripts/archive_solutions.py --classroom 2i6ng7vp --cleanup-attempts
uv run python scripts/archive_solutions.py --no-archive     # 只列出
```

`--cleanup-attempts` 会在归档成功后删除 `attempts/` 里对应关卡的旧失败存档，
让 `attempts/` 只保留当前仍未通过的关卡。TUI「执行任务」页也有同名任务。

### 按课程爬题 + 集中预生成 AI 答案（prepared/）

正常提交是「走到哪一关、当场拿哪一关问 AI」，调用分散在一整轮提交里。
`educoder_reminder.prepare` 反过来：先把一门课的题目爬下来，集中把缺答案的关卡
生成好，之后正常提交直接复用，不再烧 AI。**只写本地 `prepared/`，不提交、不触发评测。**

```bash
# 预览：只读平台，列出每关是否已有本地答案、要不要 AI（不写文件、不调 AI）
uv run python -m educoder_reminder.prepare --dry-run --classroom 2i6ng7vp

# 真跑：爬题 + 集中生成缺的答案（已有本地答案的关卡不会调用 AI）
uv run python -m educoder_reminder.prepare --classroom 2i6ng7vp
uv run python -m educoder_reminder.prepare --classroom 数据库 --experiment 视图 --limit 5
uv run python -m educoder_reminder.prepare --classroom 2i6ng7vp --no-ai   # 只爬题
uv run python -m educoder_reminder.prepare --classroom 2i6ng7vp --overwrite
```

生成了什么：

```
prepared/<实验名>/<关卡标题>/
    question.md          # 爬到的题目原文（题干 / 选项 / 目标文件 / gid / 题型）
    answer.py|.sql|.mdj|.json
    meta.json            # 课堂、gid、题型、目标路径、来源、生成时间
```

规则：

- **已有本地答案就跳过 AI**：`answers.json` / `answer/` / `solutions/` / `attempts/` /
  已生成的 `prepared/` 都算「本地已有」，命中直接打印来源并跳过；
- 已通关（`game.status==2`）的关卡、已完成/已截止的实验默认跳过（`--include-expired` 例外）；
- 不指定 `--classroom` 时只处理本学季课堂，避免历史课堂把 AI 额度烧光；
- 按题型生成：选择题由 AI 选字母；代码题先读测试文件提取参考答案，再 AI 参考模板/评测脚本/预期输出；
  图形题先用 `graders/` 里缓存的评测脚本逆向构造（不烧 AI），没有缓存才让 AI 按题面生成 `.mdj`；
- **平台只放出「当前可到达」的关卡链**（前一关没过，下一关不给详情），所以一次运行覆盖的是
  每个实验当前可到达的关卡（通常是已通关的 + 当前这一关）。通过后重跑一次就会继续补齐后面的关卡；
- 预生成的答案如果**提交没通过**，会在 `meta.json` 里标 `rejected`，提交链不再复用它
  （文件保留供人工查看），下一轮重新跑 `prepare` 或直接提交都会改用 AI / 逆向构造重做，
  不会被一份错误答案反复重交；
- `prepared/` 是可再生的中间产物，已在 `.gitignore` 里；跨机器复用请以 `answers.json` / `solutions/` 为准。

TUI「执行任务」页也有两个同名任务（题库）：**预览：课程爬题查缺答案** 和
**课程爬题 + 集中预生成 AI 答案**。

### 闭环：AI 刷一次，之后一直复用

本地没有的新课程，第一次靠 AI 刷通；答案必须能被**下一次**直接捡起来用，
否则每换一个账号 / 换一台机器就要再烧一遍 AI 调用。这条闭环由三段组成：

**1）落库**——AI 刷通后写两个地方：

| 位置 | 内容 | 说明 |
|------|------|------|
| `answers.json` | 代码 / 选择题答案（按课堂 code + 实验名 + 关卡标题） | 随仓库提交，换机器直接可用 |
| `solutions/<实验>/<关卡>/` | 代码 / 选择题 / UML 的已通关答案 | 跨账号、跨机器复用，也便于人工核对 |
| `answer/<实验>/` | UML 的 `.mdj` | 图形题的实际复用来源（`.mdj` 体积大，不塞进 answers.json） |

课堂不在 `answers.json` 里时会在落库时**自动新建条目**（带真实课堂名）。
以前这里会静默丢弃——AI 白做，下一轮又从头来。

**2）复用**——答案来源优先级（高 → 低）：

```
answers.json → answer/（UML .mdj）→ solutions/ → attempts/（未通过的存档）
            → prepared/（预生成的 AI 答案）→ 现场调用 AI
```

命中 `solutions/` 或 `prepared/` 后如果评测通过，会**回填 `answers.json`**，之后连
`solutions/` 都不用再读。所以同一门课第二轮起就是纯本地命中，零 AI 调用。

**3）换账号 / 换机器**——按课堂 **code** 匹配不到时按**课堂名**匹配；
同名课堂换班（code 变了）时沿用旧条目并更新 code，不会越存越多条。
所以只要把 `answers.json`、`answer/`、`solutions/` 一起带走（或提交进仓库），
换环境后第一次运行就全是本地命中。

对应的回归测试在 `tests/test_closed_loop.py`。

### AI 自动做题（题库缺答案时）

在 `.env` 配置（OpenAI 兼容接口，DeepSeek/OpenAI/Kimi/Qwen 等均可）：

```dotenv
AI_API_KEY='你的 key'
AI_BASE_URL='https://api.deepseek.com'
AI_MODEL='deepseek-flash'
```

不填 `AI_API_KEY` 则自动禁用；运行时可用 `--no-ai` 临时关闭。
AI 生成代码时会同时参考：题目要求、当前文件模板、评测脚本（`main.py`/`test.py`/`evaluate.py`）、
平台预期输出、以及失败后的实际报错。评测通过后答案写回 `answers.json` 或 `answer/`。

### SQL 题：必须在初始模板上补充

头歌的 SQL 关卡（MySQL 系列）编辑器里**预置了初始模板**，评测依赖它提供的上下文：

```sql
use finance1;
-- 创建包含所有保险资产记录的详细信息的视图v_insurance_detail...
-- 请用1条SQL语句完成上述任务：




/*   end  of your code  */
```

**不能整体重写**，否则会失败：

| 做法 | 结果 |
|------|------|
| 只写 `CREATE OR REPLACE VIEW ...` | ❌ `No database selected` |
| 自己编库名 `USE insurance_db;` | ❌ `Unknown database 'insurance_db'` |
| 保留 `use finance1;` + 视图定义 | ✅ 通过 |

程序里已按这个规则强制处理（`submit.py`）：

1. **`merge_sql_template(template, answer)`** —— 把答案合并进模板骨架
   - 答案缺 `use` → 补上模板的
   - 答案臆造了别的库名 → 换回模板的库名
   - 保留模板的结尾标记（`/* end of your code */`）
2. **模板缓存 `templates/<关卡>_stepN.sql`** —— 远端提交后模板会被覆盖，
   所以第一次读到就存一份，后续都用缓存的原始模板（该目录随仓库提交）
3. **`postprocess_sql`** —— 在模板合并之后再做补齐：
   - 有 `use X;` → 前面加 `CREATE DATABASE IF NOT EXISTS X;`（pod 重建库会丢）
   - 没有 `use` 且要建表 → 按题目猜库名补库
   - 没有 `use` 的纯查询/建视图 → 不动（平台预置库才有表，贸然建空库会报 `Table doesn't exist`）
   - `CREATE TABLE` 前加 `DROP TABLE IF EXISTS`（避免重复提交时表已存在）
4. **AI 提示**：明确要求保留模板的 `use`、注释和结尾标记，不要臆造库名

## 切换账号

```bash
uv run python scripts/switch_account.py                      # 交互输入
uv run python scripts/switch_account.py --account 138xxxx --password 'xxx'
uv run python scripts/switch_account.py --clear-limit        # 顺带清除登录冷却记录
uv run python -m educoder_reminder.courses                   # 验证身份
```

脚本会写入 `EDUCODER_LOGIN_ACCOUNT` / `EDUCODER_LOGIN_PASSWORD`，并清空
`EDUCODER_TOKEN` / `EDUCODER_COOKIE` / `EDUCODER_CLASSROOMS_URL`（旧账号会话）。
手工改 `.env` 时也要把这几个键置空。

切换账号后可复用的内容：

| 内容 | 复用 | 说明 |
|------|------|------|
| `answers.json` | ✅ | 按实验名/关卡标题匹配，与账号无关 |
| `answer/` 下的 `.mdj` / `res.txt` | ✅ | 按实验名和 step 匹配 |
| `graders/` 评测脚本缓存 | ✅ | 双键缓存（`gid_xxx.py` + `关卡标题_stepN.py`），换账号/换机器都能命中，随仓库提交 |
| 关卡通过状态 | ✅ | 每次从平台实时读取，自动跳过已通过 |
| 换到另一个班（课堂 code 不同） | ✅ | code 匹配不到时改按**课堂名**匹配 |
| `data/reminder.sqlite3` | ✅ | 按账号隔离 |
| 旧 Token/Cookie | ❌ | 必须清空，否则先用旧会话请求，触发身份校验失败 |

自动登录限制（同账号 30 分钟一次、24 小时最多 3 次）按账号分别记录，换账号不受影响；
同账号反复失败可用 `--clear-limit` 清冷却记录。

## 多账号队列（批量刷题）

适合帮多个同学刷题，或换账号不想手动切。串行执行，任何时刻只有一个账号在用浏览器。

```bash
# 添加账号（密码会写入 data/accounts.json，权限 600，不进 Git）
uv run python scripts/run_queue.py --add 13800000000 --note 同学A
# 不加 --password 会交互式输入（不回显）

# 查看队列和进度
uv run python scripts/run_queue.py --list

# 依次刷所有账号（默认自动跳过已完成的账号，不浪费间隔等待）
uv run python scripts/run_queue.py --apply

# 常用选项
uv run python scripts/run_queue.py --apply --only 138xxx    # 只刷某个
uv run python scripts/run_queue.py --apply --force          # 强制重跑已完成的账号
uv run python scripts/run_queue.py --apply --limit 10       # 每账号限 10 关
uv run python scripts/run_queue.py --apply --classroom D9Z6O8GR   # 覆盖所有账号
uv run python scripts/run_queue.py --apply --include-expired       # 连已截止实验也刷

# 给单个账号指定课程（用 code 或课程名，可多次传/逗号分隔）
uv run python scripts/run_queue.py --set-classrooms 138xxx --classroom D9Z6O8GR --classroom 数据库
uv run python scripts/run_queue.py --set-classrooms 138xxx   # 清空，恢复全部课堂
```

工作方式（`scripts/run_queue.py`）：

1. 账号清单 `data/accounts.json`（`[{"account","password","note"}]`，**明文保存**，
   方便查看核对；数据只在本地，`data/` 已 gitignore。想加密存储可加 `--encrypt`，
   密钥放 `data/.queue_key`）。每个账号可选带 `classrooms: [...]`，只刷指定课堂；
   不配表示全部课堂。命令行 `--classroom` 会覆盖所有账号各自的设置
2. 逐个账号：写入凭据 → **清空上一个账号的 Token/Cookie/课堂地址** →
   清该账号的登录冷却 → 按该账号自己的 `classrooms` 跑一遍 `submit_all` → 记录结果
3. 进度存 `data/queue_state.json`，每个账号跑完立即落盘，中断后可继续；
   已标记 `done` 的账号**默认自动跳过**（不会为它等账号间隔），需要重跑加 `--force`
4. 单个账号失败（密码错、验证码、网络）不影响后续账号

注意：自动登录有频率限制（同账号 30 分钟一次、24 小时 3 次），队列会在切换时自动清理
该账号的冷却记录。若某账号密码错误，会停在 `failed` 并继续下一个。

账号之间默认等待 30 分钟（`--gap 1800`）再加 0~25% 随机抖动，用于降低风险。
风控提示见下节。

### 查看队列运行状态

```bash
# 汇总：每个账号的状态/密码/上次运行，当前登录态，日志尾部
uv run python scripts/queue_status.py

# 联网检查某账号的课堂进度（较慢，会用自己的凭据登录一次）
uv run python scripts/queue_status.py --detail
uv run python scripts/queue_status.py --detail --only 138xxxxxxxx

# 配合后台运行看日志
uv run python scripts/queue_status.py --log-lines 50
```

输出示例：

```
账号            备注        状态       密码                    最后运行
18568361536             done      disbbti***            5 分钟前
        └ 提交 12 / 失败 0 / 跳过已通过 68
18336282507   zzy       failed    Zzy2920***            2 分钟前
        └ 错误：用户名或密码错误
------------------------------------------------------------------------
总计 3 个：完成 1，失败 1，待处理 1

当前登录态（.env）
配置账号：18568361536
Token：有   Cookie：有   （会话可用，无需密码登录）
登录冷却：无
```

`--detail` 会显示各课堂的「实验完成数」，例如：

```
  机器学习_2026年下半年：实验 30/30 已完成
  软件工程导论2026年下半年：实验 48/51 已完成
  合计：实验 85/88 已完成
```

### 部署到小规格服务器（实测阿里云 2C4G 1M）

可以胜任，但要**串行**跑：

| 资源 | 占用 | 说明 |
|------|------|------|
| 内存 | Chromium ~500MB + Python ~200MB | 4G 充裕，建议再加 2G swap |
| CPU | 单线程，几乎不占 | 2 核够 |
| 带宽 | 仅登录时加载网页（~3MB），其余是 JSON API（几 KB） | 1Mbps 慢但可用 |
| 磁盘 | 代码 + 缓存 <100MB | 充足 |

建议：

```bash
# 1) 装依赖
sudo apt install -y python3.12-venv
uv sync --locked
uv run playwright install chromium
sudo .venv/bin/python -m playwright install-deps chromium

# 2) 加 2G swap（可选，内存小时更稳）
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile

# 3) 队列后台跑（nohup 或 systemd，别用 tmux 之外的交互终端）
nohup uv run python scripts/run_queue.py --apply --skip-done > data/queue.log 2>&1 &
tail -f data/queue.log
```

**不要并发跑多个账号**：1Mbps 带宽 + 4G 内存撑不住并发 Chromium。

### 关于云服务器 IP 的风控风险（重要）

阿里云 ECS 的公网 IP 属于公开 ASN（如 AS37963），在 IP 情报库里被标注为
**数据中心 IP**，平台容易识别。分两层风险：

| 层面 | 影响 |
|------|------|
| 登录风控 | 部分平台对数据中心 IP 会额外要求验证码/滑块；Educoder 在云上是否如此需实测 |
| 多账号判定 | ⚠️ **主要风险**：同一 IP 连续登录多个账号，且行为模式雷同（提交相同答案），是"批量代做"的典型特征 |

风险等级（经验判断，非平台官方说明）：

| 场景 | 风险 |
|------|------|
| 同一 IP 只有 1 个账号 | 低，和家宽差别不大 |
| 同一 IP 2~3 个账号，间隔拉开 | 中，可能触发验证码 |
| 同一 IP 5 个以上账号、几分钟内连续登录 | 高，可能限流或封禁 |
| 多个账号提交完全相同的答案 | 高，平台能看到答案相似度 |

降低风险的做法：

1. **先验证单账号**：部署后先只跑一个账号，确认能正常登录、不被要求验证码，再决定是否继续
2. **拉开间隔**：`--gap` 默认 30 分钟；账号多时建议更长
3. **控制账号数**：单 IP 建议不超过 3~5 个
4. **更换弹性公网 IP**：阿里云可更换 EIP（有次数限制），能打散 IP 关联
5. 出现验证码/滑块时程序会报错停止，不会绕过——此时只能换 IP 或人工处理

如果只是自己用（1 个账号），这些限制基本无感。

## 推送与定时运行

`.env` 除认证信息外需配置：

```dotenv
SERVERCHAN_SENDKEY='在本机填写，不要提交'
UNDATED_REMINDER_MODE=once
QUOTA_POLICY=defer
SERVERCHAN_DAILY_LIMIT=5
SYNC_INTERVAL_HOURS=6
REMINDER_CHECK_INTERVAL_SECONDS=60
```

`UNDATED_REMINDER_MODE` 须选择 `once`（每个无截止时间阶段只提醒一次）或 `daily`
（北京时间每天一次）。`QUOTA_POLICY` 须选择 `defer`（次日按最新状态重判补发）或
`skip`（跳过当时到期的提醒阶段）。当前已确认使用 `once` 和 `defer`。
`SERVERCHAN_DAILY_LIMIT=5` 是程序本地保护上限，失败请求和测试通知也计入；
SC3 可按自己的免费额度调整。Turbo 免费模式最多配置 5 次，不执行任何付费订阅操作。
其他程序/官网测试消耗的额度无法计入本地统计，实际可发送次数以服务端为准。

```bash
# 只根据本地数据库预览，不访问 Educoder、不推送
uv run python -m educoder_reminder.remind preview
# 实际发送一条测试通知（占用一次本地额度）
uv run python -m educoder_reminder.remind test
# 强制同步，发送未来 5 天（120 小时）内截止的未完成作业汇总
./scripts/run.sh test-upcoming
# 同步（如到期）、检查并发送本次提醒
uv run python -m educoder_reminder.remind once
# 持续运行：6 小时全量同步；每分钟检查数据库
uv run python -m educoder_reminder.remind run
```

`test-upcoming` 排除已完成、归档、已截止及无截止时间的作业；没有符合项时发送一条
空清单说明。它占用一次发送额度，但不修改正式提醒的去重记录。后台服务运行时需先
`sudo systemctl stop educoder-reminder`，测试后 `sudo systemctl start educoder-reminder`。

运行流程：先判断本地提醒窗口，有待发事项时重新读取本人进行中课堂清单，并复核相关
课堂/作业类型的列表。完成、归档、延期、已退出或结束课堂中的旧事项不再按旧状态发送。
复核失败则暂不发送。全量同步和提醒复核均遵守归档、逾期超过 5 天过滤规则。

- 截止前 24 小时内提醒一次，1 小时内再提醒一次；首次发现不足 1 小时只发紧急阶段。
- 当前到期事项合并，紧急事项优先；超过本地 30KB 正文上限分批，其余留待下一分钟。
- 去重关联账号、课堂、作业、截止时间修改次数和提醒阶段。重启后保留记录，延期后重新提醒。
- SQLite `push_attempts` 保存请求状态，`push_events` 保存事项发送记录，不保存 SendKey。
- 每个事项/阶段最多尝试 3 次，失败后分别等待至少 5、30 分钟；每次重试先复核作业。
  请求超时或进程在服务端接受后崩溃时无法确定送达，重试可能重复通知，不能保证严格仅送达一次。
- `code=0` 表示 Server 酱接受请求，不等同于手机已显示；请在 App/微信端确认测试消息。
- 使用进程锁避免同时启动多个提醒命令。持续运行期间修改配置后需重启。

## Debian 13 定时任务部署

将项目、`.env` 及需要保留的 `data/` 复制到服务器，用运行服务的普通用户执行：

```bash
uv sync --locked
./scripts/run.sh check
```

使用自动登录时还需按上面的步骤安装 Chromium 和系统依赖。
`check` 只验证配置，不联网、不推送。
项目目录及 `.env` 需对运行用户可读，`data/` 需可写。已有数据库一并迁移可保留
同步时间和去重记录；迁移后关闭旧机器上的提醒服务，避免两台机器分别推送。

前台运行（终端退出后不会继续运行）：

```bash
./scripts/run.sh
# Ctrl+C 停止；也可使用 ./scripts/run.sh preview 预览本地待发项
```

后台与开机启动推荐 systemd。以下命令在项目目录执行，`student` 替换为服务器上实际
运行用户；服务路径自动根据项目所在位置生成，不必手工修改模板。

```bash
# 先查看将生成的服务配置，不需要 sudo，不写系统目录
python3 scripts/service.py render --user student
# 安装：以 student 检查 .env 和 data/ 权限，写入服务，暂不启动
sudo python3 scripts/service.py install --user student
# 启动并设置开机运行（会开始真实采集和推送）
sudo python3 scripts/service.py start
# 查看状态、跟踪日志
sudo python3 scripts/service.py status
sudo python3 scripts/service.py logs
# 修改 .env 或更新代码后重启
sudo python3 scripts/service.py restart
# 停止并取消开机运行
sudo python3 scripts/service.py stop
```

服务每分钟检查提醒；全量同步以数据库中最后一次成功同步时间为准，每 6 小时一次。
没有同步记录时立即采集；停机超过 6 小时后恢复会立即同步。网络故障后继续检查，
进程异常退出由 systemd 在 60 秒后重启；正常停止会释放进程锁。
日志交给 journald 管理，使用 `journalctl -u educoder-reminder.service` 查看。
数据库和去重记录保存在项目 `data/`，停止/重启服务不会删除它们。
不要同时配置 cron、另一份 systemd 服务或另一个项目副本。

`deploy/educoder-reminder.service.example` 保留为手工安装参考。

接口依据：[Turbo 官方接入说明](https://sct.ftqq.com/docs/integrations/transmission/)、
[Server 酱³ 官方文档](https://sc3.ft07.com/doc)。
