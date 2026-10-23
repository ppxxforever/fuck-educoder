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

日常采集使用 Playwright APIRequestContext 直接请求课堂接口；仅自动恢复登录时启动 Chromium。
只访问配置的本人课堂接口，固定 status=processing，遍历分页并再次排除 is_end=true。
结果保存为 data/courses.json，包括 ID、名称、课堂标识、链接和可访问状态。
认证失败、响应结构异常、重复分页或分页不完整时退出，保留上一次完整结果。
每次采集前调用 `/api/users/get_user_info.json?school=1` 获取当前登录用户的 `login`，
据此生成个人课堂地址和课堂接口参数。无需手工填写账号标识或课堂地址。
`EDUCODER_CLASSROOMS_URL` 仅作为自动维护的账号缓存：旧值与会话不一致时，会通过
账号密码重新登录，以新登录返回的 `login` 更新缓存；不会继续使用旧账号地址。

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
已标记完成（`shixun_finished_status==1`）的实验；代码题只处理单文件关卡，多文件关卡跳过以免半提交。
选择题先按 answers.json 直接提交，若格式导致未全对，会用平台在提交响应里回吐的标准答案键兜底重交一次；
代码题评测默认等待 90 秒，超时或未通过请在平台确认。

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
