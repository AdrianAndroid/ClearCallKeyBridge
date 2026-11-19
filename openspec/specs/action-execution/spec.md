# action-execution — 动作执行引擎

## Purpose

定义 normal 模式下可执行的 4 个动作的语义、参数格式、成功/失败输出。
动作由规则匹配后触发，执行结果必须可观测（日志 + 状态栏）。

## Requirements

### Requirement: 动作集合封闭

MVP 阶段 SHALL 只支持以下 4 个动作，未知动作一律拒绝执行：

```
ptt_toggle
ptt_hold
hid_send <keycode>
obs_toggle_mute
notify"<text>"
```

#### Scenario: 未知动作
- **WHEN** 规则中解析出未定义动作
- **THEN** 输出 `> ERR unknown action: xxx`，跳过执行，不影响程序运行

### Requirement: ptt_toggle

`ptt_toggle` SHALL 翻转 `ptt_state`，控制本机虚拟麦克风（PTT 推流）的开启与关闭。

#### Scenario: 从关闭到开启
- **WHEN** `ptt_state=0` 时执行 `ptt_toggle`
- **THEN** `ptt_state=1`，启动虚拟麦推流，输出 `> ACTION action=ptt_toggle → ptt_state=1`，状态栏显示 `PTT: [ON]`

#### Scenario: 从开启到关闭
- **WHEN** `ptt_state=1` 时执行 `ptt_toggle`
- **THEN** `ptt_state=0`，停止推流，状态栏显示 `PTT: [OFF]`

#### Scenario: 虚拟音频设备缺失
- **WHEN** 本机不存在可用的虚拟麦克风设备
- **THEN** 不改变 `ptt_state`，输出 `> ERR ptt unavailable: virtual mic device not found`

### Requirement: hid_send

`hid_send` SHALL 向系统发送指定键盘码（如 `F13`、`F14`），不接受鼠标与组合键表达式。

#### Scenario: 发送成功
- **WHEN** 执行 `hid_send F13`
- **THEN** 系统收到一次 F13 按键，输出 `> ACTION action=hid_send F13 ok`

#### Scenario: 非法键码
- **WHEN** 执行 `hid_send XYZ`
- **THEN** 输出 `> ERR invalid keycode: XYZ`

### Requirement: obs_toggle_mute

`obs_toggle_mute` SHALL 通过 OBS WebSocket 切换麦克风静音状态。

#### Scenario: 切换成功
- **WHEN** OBS 已运行且 WebSocket 配置正确
- **THEN** 麦克风静音状态翻转，输出 `> ACTION action=obs_toggle_mute → muted=<0|1>`

#### Scenario: OBS 未运行
- **WHEN** 连接 OBS WebSocket 失败
- **THEN** 输出 `> ERR obs unavailable: connection refused`，不影响后续按键处理

### Requirement: notify

`notify` SHALL 弹出系统桌面通知，文本取自引号内内容。

#### Scenario: 通知成功
- **WHEN** 执行 `notify"会议静音切换"`
- **THEN** 桌面出现该通知，输出 `> ACTION action=notify "会议静音切换"`

#### Scenario: 通知服务不可用
- **WHEN** 系统通知服务未运行
- **THEN** 降级为在事件流打印一行提示，不视为错误，不报 ERR

### Requirement: 执行隔离

动作执行 SHALL 异步、异常可控，不得阻塞按键采集与界面刷新。

#### Scenario: 动作抛异常
- **WHEN** 动作执行过程中抛出异常
- **THEN** 捕获并在事件流输出 `> ERR action failed: <reason>`，程序继续运行

#### Scenario: 快速连续触发
- **WHEN** 同一触发的按键被快速连按 3 次
- **THEN** 动作依次执行不丢失，界面不卡死；不做自动合并

### Requirement: ptt_hold

`ptt_hold` SHALL 在按键按下时开麦、松开时关麦（按住说话），对标 remote-mic-app 的 PTT 体验。

#### Scenario: 按住说话
- **WHEN** `call:long` 绑定 `ptt_hold` 且用户按住通话键超过长按阈值
- **THEN** 自长按判定时刻开始推流，直到该次释放才停麦；不因长按判定而立刻关闭

#### Scenario: 单击立即松开
- **WHEN** `call:click` 绑定 `ptt_hold`
- **THEN** 允许执行，但推流仅在按住的极短时间内存在；界面提示"建议 ptt_hold 绑定长按类触发"

#### Scenario: toggle 进行中触发 hold
- **WHEN** `ptt_state=1` 且 `ptt_mode=toggle` 时按下 hold 绑定键
- **THEN** 不叠加推流，输出 `> ERR ptt busy (toggle active)`，不改变状态

### Requirement: PTT 音频源

推流 SHALL 使用配置 `actions.ptt.source` 指定的输入源。

#### Scenario: 未配置
- **WHEN** `actions.ptt.source` 缺省
- **THEN** 使用 `default`（系统默认输入设备）

#### Scenario: 指定耳机麦
- **WHEN** `source=headset` 且耳机麦克风设备存在
- **THEN** 使用耳机麦克风推流

#### Scenario: 源设备不可用
- **WHEN** 指定源设备不存在，或在推流过程中被拔出
- **THEN** 停麦，输出 `> ERR ptt source unavailable: <device>`，`ptt_state=0`

### Requirement: 未来扩展（仅记录，MVP 不实现）

以下动作列入二期路线，MVP 不得实现：`shell`、`call_answer_hangup`、`call_reject`、`zoom_toggle_mute`、`teams_toggle_mute`、`busylight_set`。
