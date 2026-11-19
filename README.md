# ClearCallKeyBridge

> 漫步者 **ClearCall 200** 蓝牙话务耳机在 macOS 上的按键桥接客户端（键位映射 + 置顶工具条）。
> 仓库名 `ClearCallKeyBridge`，代码内包名仍为 `clearcall200`。

## ⚠️ 现状（务必先读）

本仓库**如实记录**了 macOS 15 上的实测结论：**这副耳机的音量 +/− 与通话键，
在用户态拿不到任何可观测事件**。界面、工具条、映射配置、权限诊断都能跑，
但"按一下键 → 亮灯 → 执行动作"这条链路目前**尚不成立**。

不是缺权限，也不是语言/框架不对——是设备类别与系统架构决定：

| 探测通道 | 实测结果 |
|---|---|
| `hidutil list` / IOHIDManager | 16 个 HID 设备中**无 EDIFIER**（耳机不是 HID 设备） |
| CGEventTap（HID + Session 双层） | 按键期间 **0 条事件**（抓到的全是鼠标点击） |
| CoreAudio 属性（volm/vmvc/mute，5ms 采样） | 按键期间 **0 条变化** |
| root 级 `log stream`（bluetoothd/bluetoothaudiod/coreaudiod） | **0 条 AVRCP 报文** |
| IOBluetooth L2CAP PSM 23（AVRCP 控制通道） | 通道存在（UUID 110F），但打开返回 `-536870212`（被系统独占） |
| HFP RFCOMM（通道 12） | 系统占用，读取 0 字节 |

结论：该耳机按键走 **AVRCP 绝对音量**，由系统 `bluetoothd` / `mediaremoted` 内部消费；
macOS 13+ 已删除可注入的 `AVRCPAgent` 进程，第三方无法在用户态拦截。

**可行的两条路**（见「路线图」）：
1. 换 **USB/HID 型耳麦**（按键即标准 HID，可读可吞，1 天可完工）；
2. 外接 **USB 蓝牙适配器 + BTstack**（用户态跑完整协议栈，可听可拦，但音频需自行接管）。

## 界面

主窗口（浅色 macOS 风格，5 页：连接 / 按键映射 / 统计 / 权限 / 关于）+ 常驻置顶小工具条。

漫步者 **ClearCall 200** 头戴式蓝牙话务耳机的按键自定义客户端（单体终端程序），
对标开源项目 [HD838A/remote-mic-app](https://github.com/HD838A/remote-mic-app) 的交互体验，
但输入源从「小米蓝牙遥控器（BLE HID）」换成「ClearCall200（AVRCP + HFP）」。

## 采集通道（macOS 实测）

- 事件拦截（CGEventTap）对本耳机无效：音量键是 AVRCP 绝对音量，不产生 NX_SYSDEFINED；耳机无 HID 节点。
- 实际生效通道：`clearcall200/vol_watch.py` 观测系统输出音量变化 → 判定 `volp`/`volm` → 写回原值实现“拦截”。
- 通话键在非通话状态无任何上报；静音/播放键由系统 HFP/AVRCP 自行处理。

## 一句话定位

- **程序本体**：单机单进程的终端客户端。蓝牙采集 → 按键解析 → 规则匹配 → 动作执行 → ASCII 界面，全在一个程序里。
- **OpenSpec**：本项目的 **模型契约规范文档**（`openspec/` 目录），是项目的唯一事实来源。
  OpenSpec **不是一个运行中的服务**，不嵌入程序，也不做分布式 Agent/Worker 拆分。

## 核心能力（MVP）

1. 识别 6 个可绑定触发源：`mute:click`、`call:click`、`call:long`、`call:double`、`volp:click`、`volp:long`、`volm:click`
2. 读取并展示 HFP 通话状态：`call_state` / `mic_mute`
3. 本地按键映射（trigger → action），配置持久化到本地文件
4. 5 个 MVP 动作：`ptt_toggle`、`ptt_hold`（按住说话）、`hid_send`、`obs_toggle_mute`、`notify`
5. **学习/测试模式（learn mode）**：逐键测试识别效果，只检测不执行，界面 + 耳机忙灯反馈，未知报文也有提示
6. ASCII 终端交互界面（状态栏 / 触发源 / 规则 / 日志流 / 命令行），含 `doctor` 自检
7. 运行期保障：单实例锁、退出清理、配置外部变更提示、事件流落盘

> ⚠️ 需要先知道的取舍：AVRCP 音量/媒体键由系统蓝牙栈直接消费，**我们能看到事件但拦不住系统改音量**，
> 所以自定义动作与原系统行为是"并存"关系。推荐把自定义优先绑到 `volp:long`、`volm:click`、`call:long`。

## 目录结构

```
EdifierClearCall200/
├── README.md                 # 本文件
├── CLAUDE.md                 # AI 开发助手强约束（Cursor/Claude 自动读取）
├── clearcall200/             # 程序本体（批 1 已落地，仅标准库）
│   ├── __main__.py           # 入口：python3 -m clearcall200
│   ├── app.py                # 编排：命令、事件分发、交互/管道两种模式
│   ├── config.py             # 配置加载与原子写入
│   ├── state.py              # 全局状态模型
│   ├── rules.py              # 规则表 + 动作校验
│   ├── parser.py             # 手势判定（长按/双击/防抖）+ 边沿事件
│   ├── actions.py            # 动作执行（批 1 占位，批 3 落地）
│   ├── ui.py                 # ASCII 界面分区渲染
│   ├── runtime.py            # 单实例锁 / 日志 / 信号清理
│   └── diag.py               # doctor 自检
├── tests/                    # 单元测试（unittest）
├── openspec/                 # ★ 模型契约规范（唯一事实来源）
│   ├── project.md            # 项目上下文与定位
│   ├── specs/
│   │   ├── device-input/     # 蓝牙采集与按键识别
│   │   ├── state-model/      # 全局状态模型
│   │   ├── key-mapping/      # 规则与配置持久化
│   │   ├── action-execution/ # 动作执行引擎
│   │   ├── learn-mode/       # 学习/测试模式
│   │   ├── terminal-ui/      # ASCII 界面规范
│   │   └── runtime-ops/      # 单实例、清理、自检
│   └── changes/              # 变更提案（迭代时使用）
├── docs/
│   ├── 开发路线.md            # 3 批交付计划与验收标准
│   ├── 界面设计.md            # ASCII 原型与布局刷新规则
│   ├── 蓝牙调试指南.md         # btmon 抓包、MUTE 逆向方法
│   └── prompts/              # 可直接粘贴给编码 AI 的提示词
├── config/
│   └── rules.example.json    # 默认规则示例（运行时生成 config/rules.json）
└── .gitignore
```

## 硬件前提（务必先读）

| 项 | 结论 |
|---|---|
| 蓝牙 | BLE 5.0，A2DP / AVRCP / HFP，仅 SBC |
| USB | Type-C **仅充电**，无 USB HID / 音频通道 |
| 按键上报 | 音量/上下曲走 AVRCP；接听挂断/静音走 HFP AT |
| 关键限制 | `mute` 事件在 HFP 通话未建立时**大概率不上报**，属于硬件行为，程序不做伪造 |
| power 键 | 属于链路生命周期，**不纳入自定义触发源** |

## 快速开始

无需第三方依赖（Python 3.9+，仅标准库）：

```bash
# 交互模式（需 TTY）
python3 -m clearcall200

# 打印一帧界面（截图 / 布局自检，不需要 TTY）
python3 -m clearcall200 --frame normal
python3 -m clearcall200 --frame learn
python3 -m clearcall200 --frame active

# 管道模式（非 TTY，逐行命令，可 grep）
printf 'test trigger=volp:long\nstate\nquit\n' | python3 -m clearcall200

# 桌面客户端：主设置窗口（配置按键）+ 常驻小工具条
python3 -m clearcall200 --ui
python3 -m clearcall200 --ui-pet      # 工具条换成桌宠

# 演示模式：每 1.5s 轮流注入识别，挂件点亮、事件流滚动
python3 -m clearcall200 --ui-demo

# 主窗口自测：约 1s 自动关闭
python3 -m clearcall200 --ui-selftest

# 常驻置顶桌面挂件（键位小工具条 320×46）
python3 -m clearcall200 --widget bar

# 桌宠形态（88×88）
python3 -m clearcall200 --widget pet

# 挂件自测：拉起后约 1s 自动关闭，并注入 4 次识别验证点亮链路
python3 -m clearcall200 --widget-selftest bar

# 事件流落盘
python3 -m clearcall200 --log /tmp/feed.log

# 单元测试
python3 -m unittest discover -s tests
python3 -m unittest tests.test_parser -v                    # 单跑一个模块
python3 -m unittest tests.test_parser.TestLongPress -v       # 单跑一个类
```

批 1 没有蓝牙采集，按键事件一律用 `test trigger=<名称>` 模拟；真机接入在批 2。

## 开发顺序

见 `docs/开发路线.md`：3 批交付（批 1 整机可跑 / 批 2 硬件接入 / 批 3 执行器与收口）。
划分依据是依赖边界：无硬件依赖 → 卡抓包 → 卡环境权限。

## 规范优先级

任何实现与 `openspec/specs/` 冲突时，**以 spec 为准**；要改行为，先改 spec 再改代码。
