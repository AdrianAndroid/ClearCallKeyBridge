# terminal-ui — ASCII 终端界面规范

## Purpose

定义程序的唯一用户界面：纯 ASCII 交互式终端面板。
界面必须实时反映状态，且不得阻塞蓝牙采集与动作执行。

## Requirements

### Requirement: 界面布局

界面 SHALL 自上而下依次为：状态栏、学习模式提示行（仅 learn）、触发源列表、规则表、事件流、命令提示符。

#### Scenario: 标准输出
- **WHEN** 程序启动完成后
- **THEN** 屏幕呈现如下结构（示意，宽度自适应 60~80 列）：

```
=============================================================
 ClearCall200 Client | follow OpenSpec
=============================================================
 📞 CALL: [IDLE] | MIC: [OPEN] | PTT: [OFF] | MODE:[NORMAL]
-------------------------------------------------------------
 Bindable Triggers:
 [0] mute:click      (HFP, only in call)
 [1] call:click
 [2] call:long
 [3] call:double
 [4] volp:click
 [5] volp:long
 [6] volm:click
-------------------------------------------------------------
 Rules:
 0: mute:click      → obs_toggle_mute
 1: call:click      → hid_send F13
 2: call:long       → notify"长按通话键"
 3: call:double     → notify"双击通话键"
 4: volp:click      → hid_send F14
 5: volp:long       → ptt_toggle
 6: volm:click      → notify"音量减"
-------------------------------------------------------------
 Feed:
 (空)
-------------------------------------------------------------
 Commands: list | set N ACTION | learn | normal | test TRIG | save | state | quit
> _
```

### Requirement: 状态栏

状态栏 SHALL 用固定 vocabulary 展示通话、麦克风、PTT、模式四项。

#### Scenario: 通话状态映射
- **WHEN** `call_state` 为以下值时
- **THEN** 状态栏显示对应标签：

```
idle    → 📞 CALL: [IDLE]
ringing → 📞 CALL: [RING]
active  → 📞 CALL: [ACTIVE]
held    → 📞 CALL: [HELD]
dialing → 📞 CALL: [DIAL]
```

#### Scenario: 麦克风与 PTT
- **WHEN** 状态变化
- **THEN** 分别渲染 `MIC: [OPEN]`/`MIC: [MUTED]` 与 `PTT: [OFF]`/`PTT: [ON]`；模式渲染 `MODE:[NORMAL]`/`MODE:[LEARN]`

#### Scenario: 设备离线
- **WHEN** `device_online=false`
- **THEN** 状态栏追加 `⚠ BT: OFFLINE`，其余字段保持最后已知值

### Requirement: 学习模式提示行

learn 模式 SHALL 在状态栏下增加一行固定提示。

#### Scenario: 进入学习模式
- **WHEN** `app_mode=learn`
- **THEN** 显示 `⚠️ LEARN MODE ACTIVE: 按键只会检测、不执行动作 | 30s auto exit`，并随倒计时更新剩余秒数

### Requirement: 事件流格式

事件流 SHALL 使用统一前缀与字段格式，便于肉眼扫描与后续日志落盘。

#### Scenario: 合法输出行
- **WHEN** 产生各类事件
- **THEN** 仅允许以下前缀：

```
> EVENT trigger=<trigger>
> ACTION action=<action expr>
> STATE call_state=<s> mic_mute=<0|1>
> [LEARN ✅] trigger=<trigger>        → <BusyLight blink ✨ | BusyLight control unsupported>
> OK <msg>
> ERR <reason>
> MODE <mode> (<reason>)
```

#### Scenario: 行数上限
- **WHEN** 事件流积累超过 200 行
- **THEN** 只保留最近 200 行（滚动丢弃最旧），防止内存与重绘开销增长

#### Scenario: 时间戳
- **WHEN** 输出 ACTION / ERR 行
- **THEN** 可选在行首加 `[HH:MM:SS]`（配置项 `ui.timestamp=true`，默认开启）

### Requirement: 命令输入

界面 SHALL 提供行内命令输入，支持列出的全部命令，非法命令给出 ERR。

#### Scenario: 命令列表
- **WHEN** 用户输入命令
- **THEN** 支持：`list`、`set N ACTION`、`learn`、`normal`、`test TRIG`、`save`、`state`、`help`、`doctor`、`debug on|off`、`reload`、`export feed`、`quit`

#### Scenario: 台面刷新不打断输入
- **WHEN** 用户正在输入命令时后台产生新事件
- **THEN** 事件写入事件流区，命令行内容不被清除

### Requirement: 非阻塞渲染

界面渲染 SHALL 与采集、执行解耦。

#### Scenario: 高频事件
- **WHEN** 1 秒内产生 20 条事件
- **THEN** 界面以 ≤ 10Hz 合并刷新，不出现闪烁卡顿，输入响应延迟 < 100ms

#### Scenario: 非 TTY 环境
- **WHEN** 程序在非 TTY（被重定向到文件、管道）下运行
- **THEN** 自动降级为逐行纯文本日志模式，不做光标控制与重绘，退出码正常

### Requirement: 无人机交互

界面 SHALL 不依赖鼠标、不使用弹窗，全部通过键盘命令驱动。

#### Scenario: 退出
- **WHEN** 输入 `quit` 或按下 Ctrl-C
- **THEN** 停止采集线程、释放虚拟麦、恢复终端状态后退出

### Requirement: 自检与调试入口

界面 SHALL 提供 `doctor`、`debug`、`reload`、`export feed` 四个辅助命令。

#### Scenario: doctor
- **WHEN** 用户输入 `doctor`
- **THEN** 逐项输出 ✅/❌ 与修复建议，覆盖：蓝牙适配器与权限、目标设备在线状态、HFP 是否被系统占用、macOS 辅助功能、输入监控及键盘事件发送权限、虚拟麦设备存在性、OBS WebSocket 连通性、忙灯是否可控、单实例锁状态

#### Scenario: debug
- **WHEN** 用户输入 `debug on` / `debug off`
- **THEN** 开关原始报文摘要输出（默认 off），不影响正常事件流

#### Scenario: reload
- **WHEN** 用户输入 `reload`
- **THEN** 重新读取配置文件；若内存中有未保存改动（`dirty=true`），先要求用户确认，不静默丢弃

#### Scenario: export feed
- **WHEN** 用户输入 `export feed`
- **THEN** 把最近 200 行事件流导出为文本（路径输出在屏幕上），便于贴给他人分析

### Requirement: 事件流落盘

程序 SHALL 支持把事件流写入文件，供事后分析。

#### Scenario: 命令行参数
- **WHEN** 以 `--log /path/to/feed.log` 启动
- **THEN** 事件流同时写入该文件（行格式与非 TTY 降级输出一致），界面仍正常渲染

#### Scenario: 写入失败
- **WHEN** 日志路径不可写
- **THEN** 界面提示 `> ERR log disabled: <reason>`，程序继续运行
