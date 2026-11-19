# AGENTS.md

本项目规范见 `openspec/`，AI 开发约束见 `CLAUDE.md`（`.cursorrules` 与其保持一致）。开工前先读：
1. `CLAUDE.md`
2. `openspec/project.md`
3. `openspec/specs/*/spec.md`（7 个 capability：device-input / state-model / key-mapping / action-execution / learn-mode / terminal-ui / runtime-ops）

## 非显然的硬约束（违反即 bug）

- 单体单进程终端程序。`openspec/` 是模型规范文档，**不是运行中的服务**：禁止实现 TCP 中枢 / Agent-Worker 分布式 / Web GUI。
- 目标平台 Linux（BlueZ + btmon）；macOS 只留适配入口。
- 采集线程、UI 渲染、定时器必须解耦，UI 不得阻塞采集。
- `mute:click` 仅在 HFP `call_state != idle` 时存在；空闲时不产出事件，**不得软件伪造**。
- learn 模式必须完全跳过规则匹配与动作执行，只做检测 + 忙灯反馈（不可控时降级文案），30s 超时回 normal。
- MVP 动作集合封闭为 5 个（`ptt_toggle` / `ptt_hold` / `hid_send` / `obs_toggle_mute` / `notify`），一条 trigger 只绑一个 action。
- `ptt_hold` 依赖 press/release 边沿事件；断连、release 丢失、退出时**必须强制停麦**。
- AVRCP 音量/媒体键的默认行为无法被拦截（P0-3 决策 A：并存），不得宣称"已拦截"。
- 改行为先改 spec（走 `openspec/changes/`），再改代码。

## 工程命令（批 1 已可用）

```bash
python3 -m clearcall200                          # 交互模式（需 TTY）
python3 -m clearcall200 --frame normal|active|learn  # 打印一帧界面（无 TTY 也能跑）
printf 'test trigger=volp:long\nquit\n' | python3 -m clearcall200   # 管道模式
python3 -m clearcall200 --config config/rules.json --log /tmp/feed.log

python3 -m clearcall200 --ui                   # 主设置窗口 + 常驻工具条（关闭主窗口=保活）
python3 -m clearcall200 --widget bar            # 常驻置顶小工具条（320×46）
python3 -m clearcall200 --widget pet            # 桌宠形态（88×88）
python3 -m clearcall200 --widget-selftest bar   # 挂件自测：约 1s 自动关闭

python3 -m unittest discover -s tests            # 全部单测
python3 -m unittest tests.test_parser -v         # 单跑一个模块
python3 -m unittest tests.test_parser.TestLongPress -v  # 单跑一个类
```

无第三方依赖，仅 Python 3.9+ 标准库。运行时生成 `config/rules.json`（已 gitignore）。

## 参考文档

- 开发节奏与验收：`docs/开发路线.md`
- 界面原型与布局刷新规则：`docs/界面设计.md`
- btmon 抓包与 MUTE 逆向方法：`docs/蓝牙调试指南.md`
- 已知功能缺口与待定事项：`openspec/changes/2026-11-19-mvp-gaps.md`
