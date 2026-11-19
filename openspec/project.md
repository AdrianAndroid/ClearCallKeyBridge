# Project Context — EdifierClearCall200

## 项目是什么

一个单体终端客户端，把漫步者 **ClearCall 200** 头戴式蓝牙话务耳机的按键变成可自定义的控制源：
按键事件驱动本地动作（PTT 按住说话、发送 HID 热键、切换 OBS 静音、桌面通知），
并在终端界面实时呈现话务通话状态（来电 / 通话中 / 保持 / 静音）。

## 为什么做

`remote-mic-app`（小米蓝牙遥控器 + PTT）证明了"把一个小设备的按键变成生产力工具"这件事的价值。
但它的输入源是 BLE HID 遥控器，有独立私有 GATT 服务，按键随时可上报。
本项目的输入源是话务耳机，走 AVRCP + HFP，**没有 HID 通道**，系统无法直接把这些按键映射成自定义快捷键，
因此需要一个自己的采集 + 映射 + 执行程序。

## 架构定位（重要）

```
┌──────────────────────────────────────────────────────┐
│ 单体终端客户端（单进程，本地运行）                     │
│  bluetooth → parser → rules → state → executor → ui  │
└──────────────────────────────────────────────────────┘
        ↑ 严格按 openspec/specs/ 中定义的模型实现
OpenSpec = 模型契约文档（openspec/ 目录），不是服务、不是分布式
```

明确排除（MVP 阶段）：
- 不实现常驻 TCP/WS 中心服务
- 不实现 Agent / Worker 多端拆分
- 不实现 Web 面板 / 图形 GUI

将来若要演进为分布式，只需复用本规范的事件、状态、动作命名，即可派生协议，而不必重新设计模型。

## 目标平台

- MVP：macOS，单进程本地程序。
- 真实蓝牙按键监听的可用接口和设备支持范围须经证据验证；Linux 不属于当前 MVP 交付要求。

## 领域术语

| 术语 | 含义 |
|---|---|
| trigger | 可绑定的按键事件，形如 `volp:long` |
| action | 可执行的动作，形如 `ptt_toggle` |
| rule | trigger → action 的一条映射 |
| app_mode | 程序运行模式：normal / learn |
| call_state | HFP 通话状态 |
| mic_mute | 耳机侧麦克风静音状态 |
| busy_light | 耳机上的忙灯（勿扰指示灯） |
| learn mode | 学习/测试模式，只检测按键不执行动作 |

## 规范清单

| Capability | 路径 | 说明 |
|---|---|---|
| device-input | `specs/device-input/spec.md` | 蓝牙采集、报文解析、按键识别 |
| state-model | `specs/state-model/spec.md` | 全局状态字段与流转 |
| key-mapping | `specs/key-mapping/spec.md` | 规则表与配置持久化 |
| action-execution | `specs/action-execution/spec.md` | 5 个 MVP 动作语义 |
| learn-mode | `specs/learn-mode/spec.md` | 学习/测试模式行为 |
| terminal-ui | `specs/terminal-ui/spec.md` | ASCII 界面布局与输出格式 |
| runtime-ops | `specs/runtime-ops/spec.md` | 单实例、退出清理、配置变更、doctor 自检 |
| desktop-widget | `specs/desktop-widget/spec.md` | 常驻置顶小挂件（键位工具条 / 桌宠）与按键点亮反馈 |

## 硬件约束（决定了很多设计的上限）

1. ClearCall200 只有蓝牙 5.0，Type-C 仅充电，**没有 USB HID / USB 音频**，只能蓝牙抓包。
2. 音量、上下曲 → AVRCP Passthrough；接听、挂断、静音 → HFP AT。
3. **`mute` 事件在 HFP 通话未建立时大概率不上报**：耳机本地改灯，但链路不发包。
   这是硬件行为，程序必须如实反映（界面标注备注 + 学习模式下无反馈），不得伪造或猜测。
4. `power` 键直接管理链路（开关机 / 配对），长按会断连导致采集端掉线，**不纳入自定义触发源**。
5. 支持一拖二，HFP 链路可能切换，解析需按连接句柄区分。
