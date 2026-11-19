# device-input — 蓝牙采集与按键识别

## Purpose

从操作系统的蓝牙栈获取 ClearCall200 的 AVRCP / HFP 报文，翻译成 OpenSpec 定义的标准化 `trigger` 与 `call_state`，
这是整个程序的唯一输入源。采集层不做任何决策、不执行任何动作。

## Requirements

### Requirement: 设备绑定

采集层 SHALL 只监听指定目标设备，避免其他蓝牙设备的按键串入。

#### Scenario: 目标设备已连接
- **WHEN** 目标耳机（按 MAC 地址匹配）已连接且是本机音频设备
- **THEN** 采集层开始监听该设备的 AVRCP 与 HFP 事件，并向状态层上报 `online`

#### Scenario: 目标设备断开
- **WHEN** 目标耳机断连或蓝牙服务不可用
- **THEN** 采集层上报 `offline`，界面顶部标注断连，重连后自动恢复监听，不需要用户重启程序

#### Scenario: 非目标设备
- **WHEN** 本机连接了另一副蓝牙耳机并按键
- **THEN** 采集层必须忽略，不产生任何 trigger

### Requirement: 触发源识别

采集层 SHALL 将原始按键报文翻译为下列 7 个标准 trigger，命名固定不可改：

```
mute:click    call:click    call:long    call:double
volp:click    volp:long     volm:click
```

#### Scenario: AVRCP 音量键
- **WHEN** 收到 AVRCP Passthrough 的音量加/减
- **THEN** 分别识别为 `volp:click` / `volm:click`

#### Scenario: AVRCP 长按
- **WHEN** 音量加的按下持续超过长按阈值
- **THEN** 识别为 `volp:long`，且该次按压的抬起不再额外产生 `volp:click`

#### Scenario: HFP 通话键
- **WHEN** 收到 HFP 通话键的短按 / 长按 / 双击
- **THEN** 分别识别为 `call:click` / `call:long` / `call:double`；双击判定窗口内的两次短按不得额外产生两条 `call:click`

#### Scenario: HFP 静音键（实为通话中「电源键单击」）
- **WHEN** 收到 HFP 静音（AT+CMUT 类）指令且 `call_state` 非 idle
- **THEN** 识别为 `mute:click`
- **NOTE** 硬件无独立静音键；该事件物理来源是**电源键在通话状态下的单击**（见 `docs/按键功能对照.md`）

#### Scenario: 静音键在空闲状态被按下
- **WHEN** `call_state` 为 idle 且用户按下静音键
- **THEN** 采集层不产生任何 trigger（硬件不上报），界面不显示检测结果；不得由软件伪造该事件

### Requirement: 时序阈值

长按与双击的判定阈值 SHALL 可配置，并有防抖。

#### Scenario: 默认阈值
- **WHEN** 程序使用默认配置运行
- **THEN** 长按阈值 ≥ 1.5s，双击间隔窗口 ≤ 500ms，同一物理按键 50ms 内的重复报文视为抖动被丢弃

### Requirement: 通话状态采集

采集层 SHALL 持续上报 HFP 通话状态与麦克风静音状态。

#### Scenario: 来电
- **WHEN** 收到 HFP RING
- **THEN** 上报 `call_state=ringing`

#### Scenario: 通话建立 / 保持 / 结束
- **WHEN** 收到通话建立、保持、挂断的 HFP 状态变化
- **THEN** 分别上报 `call_state=active` / `held` / `idle`

#### Scenario: 静音状态变化
- **WHEN** 耳机侧麦克风静音状态变化
- **THEN** 上报 `mic_mute=0|1`

### Requirement: 忙灯能力探测

采集层（或 busylight 模块）SHALL 探测耳机是否支持指令控制忙灯，并缓存探测结果。

#### Scenario: 支持忙灯控制
- **WHEN** 首次尝试下发忙灯指令成功
- **THEN** 缓存 `busylight_capable=true`，供学习模式反馈使用

#### Scenario: 不支持忙灯控制
- **WHEN** 下发忙灯指令失败或返回不支持
- **THEN** 缓存 `busylight_capable=false`，后续不再重试下发，调用方降级为纯文本反馈，且不产生错误日志噪音

### Requirement: 平台实现

MVP SHALL 以 macOS 为目标平台。采集方式 SHALL 基于 macOS 可用接口和实际证据选择，不预设系统必然暴露 AVRCP / HFP 原始事件。

#### Scenario: macOS 采集
- **WHEN** 目标设备连接且所需接口与权限可用
- **THEN** 在独立线程或协程中采集可获得的设备事件，不阻塞界面；仅对证据足够的事件生成 trigger

#### Scenario: 接口或权限不可用
- **WHEN** macOS 不提供所需事件、依赖缺失或权限不足
- **THEN** 明确提示限制，程序仍可运行，`test` 与界面调试仍可使用；不得伪造事件

### Requirement: 手势判定与时延

判定顺序 SHALL 为：按下即记录 → 达到长按阈值立即判定 long → 释放时若不构成 long，再进入 click / double 判定。

#### Scenario: 该键未绑定 double 规则
- **WHEN** `call:click` 有绑定、`call:double` 无绑定
- **THEN** 释放时立即判定 `call:click`，不产生额外延迟

#### Scenario: 该键已绑定 double 规则
- **WHEN** `call:double` 有绑定
- **THEN** 单击必须等 `double_click_ms` 窗口结束再判定；`ui.show_latency_hint=true` 时日志标注 `(waited double window)`

#### Scenario: learn 模式下的判定
- **WHEN** `app_mode=learn`
- **THEN** 一律按"存在 double 规则"判定（学习目的是验证全部手势），并在日志标注等待原因

#### Scenario: 长按不重复产 click
- **WHEN** 长按已判定
- **THEN** 该次释放不再产生 click，也不进入 double 窗口

### Requirement: 边沿事件（内部）

解析层 SHALL 额外产出按下 / 松开边沿事件，供按住类动作使用；边沿事件不进入 UI 事件流。

#### Scenario: 边沿输出
- **WHEN** 用户按下或松开按键
- **THEN** 内部产出 `edge press key=volp` / `edge release key=volp`，携带单调递增时间戳

#### Scenario: 断连补发释放
- **WHEN** 按键处于按下状态时设备断连
- **THEN** 补发一次 `edge release`，保证按住类动作不会卡在开启状态

### Requirement: 未知报文可诊断

解析层 SHALL 记录无法映射为已知 trigger 的报文，并在 learn 模式或 `debug on` 时输出。

#### Scenario: learn 模式遇到未知报文
- **WHEN** `app_mode=learn` 且收到无法识别的报文
- **THEN** 输出 `> [LEARN ⚠] unknown pdu: <cid/opcode 摘要>`

#### Scenario: normal 模式默认静默
- **WHEN** `app_mode=normal` 且 `debug=off`
- **THEN** 静默丢弃未知报文，不刷屏

#### Scenario: debug 开启
- **WHEN** 执行 `debug on` 后收到任何报文
- **THEN** 输出原始报文摘要（方向、CID、opcode 或 AT 文本）到事件流

### Requirement: macOS 音量观测的证据边界

系统输出音量变化 MAY 用于诊断，但不能单独证明变化来自目标耳机或对应某个物理按键。只有能够可靠归因到目标设备和手势时，采集层才可生成对应 trigger；不得由音量变化伪造按下或释放边沿。

#### Scenario: 音量变化来源不明
- **WHEN** 系统音量变化但无法确认来源
- **THEN** 不将其作为真实耳机按键事件；可在诊断中显示该变化

#### Scenario: 没有释放边沿
- **WHEN** 可观察到的信号不包含可靠的释放边沿
- **THEN** 不把该信号用于依赖按下和释放的 `ptt_hold`
