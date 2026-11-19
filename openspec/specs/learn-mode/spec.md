# learn-mode — 学习/测试模式

## Purpose

给用户一个「逐键验证」的场景：进入 learn 模式后，按下耳机上的每一个按键，
程序只做检测与反馈（界面提示 + 忙灯闪烁），不执行任何绑定动作。
用户据此确认哪些键能被抓取、哪个键受硬件限制、自己的配置是否值得绑定。

这是本项目区别于 remote-mic-app 的重点功能之一。

## Requirements

### Requirement: 进入与退出

程序 SHALL 支持通过命令进入 / 退出学习模式。

#### Scenario: 进入
- **WHEN** 用户在 normal 模式输入 `learn`
- **THEN** `app_mode=learn`，状态栏标记 `MODE:[LEARN]`，出现提示行 `⚠️ LEARN MODE ACTIVE: 按键只会检测、不执行动作 | 30s auto exit`

#### Scenario: 手动退出
- **WHEN** 用户在 learn 模式输入 `normal`
- **THEN** 立即回到 `app_mode=normal`，状态栏恢复 `MODE:[NORMAL]`

#### Scenario: 超时退出
- **WHEN** learn 模式持续 30 秒（可配置）
- **THEN** 自动回 normal，事件流输出 `> MODE normal (learn timeout)`

### Requirement: 不执行任何动作

learn 模式下 SHALL 完全跳过规则匹配与动作执行。

#### Scenario: 按键命中已有规则
- **WHEN** `app_mode=learn` 且 `volp:long` 已有绑定 `ptt_toggle`
- **THEN** 不执行 `ptt_toggle`，`ptt_state` 不变，仅输出学习检测日志

#### Scenario: 已开启的 PTT
- **WHEN** 进入 learn 模式前 `ptt_state=1`
- **THEN** 保持原状，不在进入时强制关闭；界面照实显示 `PTT: [ON]`

### Requirement: 检测反馈（界面）

每次成功识别 trigger SHALL 在事件流打印一条带标记的检出日志。

#### Scenario: 检出成功
- **WHEN** learn 模式下识别到 `call:click`
- **THEN** 输出 `> [LEARN ✅] trigger=call:click        → BusyLight blink ✨`

#### Scenario: 长按检出
- **WHEN** learn 模式下按住通话键超过长按阈值
- **THEN** 输出一条 `> [LEARN ✅] trigger=call:long → ...`，不得在同一次按压中再输出 `call:click`

#### Scenario: 硬件不上报
- **WHEN** 用户空闲状态（`call_state=idle`）按下 `mute` 键
- **THEN** 不输出任何 LEARN 行（耳机未上报）。界面在触发源列表该行已标注 `(HFP, only in call)`，用户可自行对照判断

### Requirement: 检测反馈（物理忙灯）

learn 模式 SHALL 在检出成功时尝试让耳机忙灯闪烁一次，作为物理反馈。

#### Scenario: 忙灯可控
- **WHEN** `busylight_capable=true` 且检出成功
- **THEN** 下发一次短闪烁（约 200ms，次数 1~2 次），事件流仍打印 `→ BusyLight blink ✨`

#### Scenario: 忙灯不可控
- **WHEN** `busylight_capable=false`
- **THEN** 输出 `> [LEARN ✅] trigger=xxx        → BusyLight control unsupported`，不重试、不报错、不阻塞

### Requirement: 状态采集不受影响

learn 模式 SHALL 继续采集通话状态并刷新状态栏。

#### Scenario: 通话中的学习模式
- **WHEN** learn 模式下 `call_state` 变为 `active`
- **THEN** 状态栏立即更新 `📞 CALL: [ACTIVE]`，事件流可输出 STATE 行；这不属于"执行动作"，是允许的

### Requirement: 学习模式不写入规则

MVP 阶段 learn 模式 SHALL 只做检测，不提供「按键 → 绑定」的学习式自动配置。

#### Scenario: 用户想改绑定
- **WHEN** 用户在 learn 模式确认了某个 trigger 可识别
- **THEN** 需 `normal` 退出后使用 `set N ACTION` 修改绑定（界面命令区保持可见提示）

### Requirement: 未知报文可视化

learn 模式 SHALL 把收到但无法识别的报文展示出来，避免"硬件不上报"与"解析不出来"混淆。

#### Scenario: 未知报文
- **WHEN** learn 模式下收到无法映射为已知 trigger 的报文
- **THEN** 输出 `> [LEARN ⚠] unknown pdu: <cid/opcode 摘要>`，并累计计数（界面可显示 `unknown=3`）

#### Scenario: 完全无报文
- **WHEN** learn 模式下按下某键，既无 LEARN ✅ 也无 LEARN ⚠
- **THEN** 保持静默（说明耳机未上报），界面备注 `(HFP, only in call)` 已可解释原因

### Requirement: 判定延迟可见

learn 模式下 SHALL 标注因双击窗口导致的判定延迟，避免用户误判"按键没反应"。

#### Scenario: 等待双击窗口
- **WHEN** learn 模式下单击通话键并等待双击窗口
- **THEN** 输出 `> [LEARN ✅] trigger=call:click        → BusyLight blink ✨ (waited double window)`
