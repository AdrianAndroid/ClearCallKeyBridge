# state-model — 全局状态模型

## Purpose

程序内部所有对外可见的状态集中定义在此。界面、规则引擎、执行器、学习模式均读写同一份状态，
不允许各自维护私有状态副本。状态命名固定，作为项目术语基线。

## Requirements

### Requirement: 状态字段

程序 SHALL 维护以下全局状态字段，字段名不可更改：

| 字段 | 类型 | 取值 | 说明 |
|---|---|---|---|
| `app_mode` | enum | `normal` \| `learn` | 运行模式 |
| `call_state` | enum | `idle` \| `ringing` \| `active` \| `held` \| `dialing` | HFP 通话状态 |
| `mic_mute` | int | `0` \| `1` | 耳机侧麦克风静音 |
| `ptt_state` | int | `0` \| `1` | PTT 虚拟麦状态 |
| `device_online` | bool | `true` \| `false` | 耳机是否在线 |
| `learn_remain` | int | 秒 | 学习模式剩余秒数 |
| `busylight_capable` | bool | `true` \| `false` | 忙灯是否可控 |

#### Scenario: 初始状态
- **WHEN** 程序启动
- **THEN** `app_mode=normal`、`call_state=idle`、`mic_mute=0`、`ptt_state=0`、`device_online=false`

### Requirement: 状态变更通知

任何状态字段变化 SHALL 触发一次状态刷新，并按 `terminal-ui` 规范输出一条 `STATE` 行。

#### Scenario: 状态变化输出
- **WHEN** `call_state` 由 `ringing` 变为 `active`
- **THEN** 界面状态栏立即刷新，事件流新增 `> STATE call_state=active mic_mute=0`

#### Scenario: 重复相同状态
- **WHEN** 上报的状态与当前完全一致
- **THEN** 不输出 STATE 行，避免日志刷屏

### Requirement: 模式互斥

`app_mode` 决定按键事件的分发路径，两种模式互斥。

#### Scenario: normal 模式
- **WHEN** `app_mode=normal` 且识别到合法 trigger
- **THEN** 进入规则匹配并执行动作

#### Scenario: learn 模式
- **WHEN** `app_mode=learn` 且识别到合法 trigger
- **THEN** **不进入规则匹配、不执行任何动作**，仅输出学习检测日志并按能力闪烁忙灯

### Requirement: PTT 状态独立

`ptt_state` SHALL 由 `ptt_toggle` 动作维护，与 `mic_mute`、`call_state` 无耦合。

#### Scenario: PTT 切换
- **WHEN** 执行 `ptt_toggle`
- **THEN** `ptt_state` 在 0/1 间翻转，界面状态栏同步更新，事件流输出对应 ACTION

#### Scenario: 通话中切换 PTT
- **WHEN** `call_state=active` 时执行 `ptt_toggle`
- **THEN** 允许执行，不改写 `mic_mute`，两者各自独立展示

### Requirement: 学习模式倒计时

`app_mode=learn` 时 SHALL 启动倒计时，`learn_remain` 每 1 秒递减。

#### Scenario: 倒计时结束
- **WHEN** `learn_remain` 减至 0
- **THEN** 自动切回 `app_mode=normal`，输出提示 `> MODE normal (learn timeout)`

#### Scenario: 手动退出
- **WHEN** 用户在 learn 模式输入 `normal`
- **THEN** 立即停止倒计时并切回 `app_mode=normal`

#### Scenario: 重复进入
- **WHEN** 已在 learn 模式时再次输入 `learn`
- **THEN** 重置倒计时为 30s，不叠加多个定时器

### Requirement: 断连容错

设备断连时状态 SHALL 明确反映，且不影响程序存活。

#### Scenario: 采集线程异常
- **WHEN** 蓝牙采集线程崩溃或抛出异常
- **THEN** 程序不退出，标记 `device_online=false`，界面提示，其余功能（`test`、规则管理）继续可用

### Requirement: PTT 模式区分

除 `ptt_state` 外 SHALL 记录 `ptt_mode`（`toggle` | `hold`），用于区分"按一下开关"与"按住说话"。

#### Scenario: toggle 推流
- **WHEN** 执行 `ptt_toggle`
- **THEN** `ptt_state` 翻转，`ptt_mode=toggle`

#### Scenario: hold 推流
- **WHEN** `ptt_hold` 收到 `edge press`
- **THEN** `ptt_state=1`、`ptt_mode=hold`；收到对应 `edge release` 时 `ptt_state=0`

#### Scenario: 模式切换清理
- **WHEN** `ptt_state=1` 且 `ptt_mode=hold` 时执行 `ptt_toggle`
- **THEN** 先停麦再翻转（终态 `ptt_state=0`），两种模式不得叠加

### Requirement: 强制停麦

以下情况 SHALL 强制结束推流并置 `ptt_state=0`，防止卡死在开麦状态。

#### Scenario: 设备断连
- **WHEN** 推流过程中设备断连
- **THEN** 立即停麦，输出 `> ERR ptt stopped: device offline`

#### Scenario: 释放丢失兜底
- **WHEN** `ptt_hold` 开启后超过 `ptt_hold_max_sec`（默认 120s）未收到 release
- **THEN** 自动停麦并提示

#### Scenario: 程序退出
- **WHEN** 用户 `quit` 或收到 SIGTERM / SIGINT
- **THEN** 无论何种 `ptt_mode`，先停麦再退出
