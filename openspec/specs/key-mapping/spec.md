# key-mapping — 规则表与配置持久化

## Purpose

定义 trigger → action 的映射数据模型、默认规则、持久化格式与读写命令。
规则表是 normal 模式下按键分发到动作的唯一依据。

## Requirements

### Requirement: 规则数据模型

每条规则 SHALL 包含：`index`（序号）、`trigger`（触发源）、`action`（动作表达式）、`note`（可选备注）。

#### Scenario: 规则结构
- **WHEN** 程序加载规则
- **THEN** 每条规则形如 `{index, trigger, action}`，其中 trigger 必须属于 device-input 定义的可绑定集合

### Requirement: 序号绑定

规则 SHALL 按固定的 7 个触发源序号排列，序号与触发源一一固定对应，便于命令行 `set N action` 操作。

#### Scenario: 序号表
- **WHEN** 界面展示规则
- **THEN** 显示如下固定序号：

```
0: mute:click    (HFP, only in call)
1: call:click
2: call:long
3: call:double
4: volp:click
5: volp:long
6: volm:click
```

### Requirement: 默认规则

程序首次运行（无配置文件）SHALL 加载并在启动时写入以下默认规则：

```
0: mute:click   → obs_toggle_mute
1: call:click   → hid_send F13
2: call:long    → notify"长按通话键"
3: call:double  → notify"双击通话键"
4: volp:click   → hid_send F14
5: volp:long    → ptt_toggle
6: volm:click   → notify"音量减"
```

#### Scenario: 首次启动
- **WHEN** 配置文件不存在
- **THEN** 使用默认规则，并在 `config/rules.json` 写出，界面提示「已生成默认配置」

#### Scenario: 配置文件损坏
- **WHEN** 配置文件存在但 JSON 解析失败或字段非法
- **THEN** 备份原文件为 `rules.json.bak`，回退默认规则，界面给出警告，不崩溃

### Requirement: 修改规则

用户 SHALL 能通过命令修改单条规则，修改只在内存生效，需 `save` 才落盘。

#### Scenario: 修改成功
- **WHEN** 执行 `set 5 ptt_toggle`
- **THEN** 第 5 号触发源绑定改为 `ptt_toggle`，界面立即刷新规则表，并提示 `> OK dirty=true (输入 save 生效)`

#### Scenario: 非法动作
- **WHEN** 执行 `set 3 xxx_invalid`
- **THEN** 拒绝修改，输出 `> ERR unknown action: xxx_invalid`，规则保持原值

#### Scenario: 非法序号
- **WHEN** 执行 `set 9 notify"x"`
- **THEN** 输出 `> ERR index out of range (0-6)`

### Requirement: 持久化

`save` SHALL 将当前内存规则完整写入本地配置文件。

#### Scenario: 保存
- **WHEN** 执行 `save`
- **THEN** 写出配置文件（JSON，含 schema 版本、设备 MAC、7 条规则），输出 `> OK saved to config/rules.json`，`dirty=false`

### Requirement: 配置文件格式

配置文件 SHALL 为 JSON，含版本号与设备标识，便于将来迁移。

#### Scenario: 文件结构
- **WHEN** 查看 `config/rules.json`
- **THEN** 结构形如：

```json
{
  "version": 1,
  "device": "E8:AA:BB:CC:DD:EE",
  "timing": { "long_press_ms": 1500, "double_click_ms": 500, "debounce_ms": 50 },
  "learn_timeout_sec": 30,
  "ptt_hold_max_sec": 120,
  "ui": { "show_latency_hint": true, "timestamp": true, "feed_max_lines": 200 },
  "rules": [
    { "index": 0, "trigger": "mute:click", "action": "obs_toggle_mute" },
    { "index": 1, "trigger": "call:click", "action": "hid_send F13" }
  ],
  "actions": {
    "ptt": { "source": "default" },
    "obs": { "host": "127.0.0.1", "port": 4455, "password": "" }
  }
}
```

### Requirement: 与系统默认行为并存（P0-3 决策 A）

由于 AVRCP 音量与媒体键由系统蓝牙栈 + 音频服务直接消费，程序**无法阻止**系统执行默认行为。
规范 SHALL 采用"并存"策略：自定义动作与原系统行为同时发生，并如实告知用户。

#### Scenario: 音量键绑定自定义动作
- **WHEN** 用户把 `volp:click` 绑定为 `hid_send F14`
- **THEN** F14 会发送，同时系统音量仍会 +1；界面与文档必须明确说明这一点，不得宣称"已拦截"

#### Scenario: 空闲状态按通话键
- **WHEN** `call:click` 绑定自定义动作且 `call_state=idle`
- **THEN** 自定义动作执行，同时系统媒体可能被播放/暂停（视耳机是否上报该事件而定）

#### Scenario: 推荐绑定位
- **WHEN** 用户追求"尽量不与系统默认冲突"
- **THEN** 文档与界面推荐优先使用 `volp:long`、`volm:click`、`call:long` 这类默认行为较弱或无害的触发源

#### Scenario: 后续可选增强
- **WHEN** 用户需要抑制音量默认行为
- **THEN** 通过配置 `actions.volume_rollback.enabled`（默认 false）启用"检测后回滚音量"；该能力不属于 MVP 默认行为，开启后允许出现抖动

### Requirement: 软件限制

MVP 阶段一条 trigger SHALL 只绑定一个 action。

#### Scenario: 尝试绑定多个
- **WHEN** 用户执行 `set 5 "ptt_toggle,notify\"hi\""`
- **THEN** 输出 `> ERR multiple actions not supported in MVP`，不修改规则
