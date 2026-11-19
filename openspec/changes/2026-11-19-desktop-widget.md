# 2026-11-19 · 新增桌面挂件形态（键位浮条 / 桌宠）

## 背景 / 动机

当前程序是纯终端界面。实际通话场景里用户不会一直盯着终端，但需要**即时反馈**：
"我刚才按的那个键，程序到底识别成了单击还是长按？"——终端里要翻日志才知道。

挂件用最低成本解决这件事：常驻置顶的小浮条，按哪个键哪个键亮一下，同时打出识别结果。

## 影响面

- 涉及 capability：新增 `desktop-widget`；`terminal-ui` 不变（终端仍是主界面）
- 涉及模块与文件：新增 `clearcall200/widget.py`；`app.py` 增加边沿/trigger 回调挂点；
  `__main__.py` 增加 `--widget`
- 是否影响已有术语或状态字段：**否**。完全复用 `call_state / mic_mute / ptt_state / ptt_mode / app_mode`

## 规范变更

### ADDED Requirements

见 `openspec/specs/desktop-widget/spec.md`（两种形态、常驻置顶、按键点亮、手势徽标、
状态镜像、PTT 进度、单进程协同）。

### MODIFIED Requirements

- `CLAUDE.md` 原文"禁止 Web GUI" → 调整为"终端为主 UI；允许 Tk 常驻挂件；仍禁止 Web / Electron"。
- `terminal-ui` 不变：挂件不是替代品，二者共用同一状态源。

## 兼容性

- 不改变配置文件结构，不需要迁移。
- 不改变触发源、动作集合、命令集。
- 挂件形态下仍可用命令行参数 `--config/--log`。

## 代码落地清单

- `clearcall200/widget.py`：`KeyBarWidget` / `PetWidget`（Tk，零第三方依赖）
- `clearcall200/app.py`：`edge_listener` / `trigger_listener` 两个回调挂点；`run(mode=...)`
- `clearcall200/__main__.py`：`--widget bar|pet`、`--widget-selftest`
- `tests/test_widget.py`：手势标签映射、徽标计时、PTT 进度换算等纯逻辑单测
- `docs/界面设计.md`：补挂件的 ASCII 原型与状态色表

## 状态

已批准（本轮直接落地）。

## 追加（同日）：界面语言对齐开源参考 + 真实采集接线

背景：用户两次否决深色界面，要求按 `HD838A/remote-mic-app` 的浅色 macOS 风格重做，并强调"按了按键要亮灯"。

行为变更（均已实现）：

1. 主设置窗口视觉：浅色三栏式（左图标栏 5 项 / 标题「按键映射」+ 启用开关 / 右上设备卡 / 中间耳机实物图 / 左右按键卡片（单击·双击·长按）/ 底栏状态点+学习模式开关+保存+恢复默认）。
2. 常驻工具条同步改浅色，与主窗口同一套色板（BG `#FCFCFD`、BORDER `#DFDFE4`、ACCENT `#0A84FF`）。
3. 真实采集闭环：`MediaKeySource`（CGEventTap，NX_SYSDEFINED/AUX）→ 线程安全队列 → `App.pump_edges()` → `GestureParser` → `edge_listener` / `trigger_listener` → 主窗口卡片高亮 + 工具条胶囊高亮 + 手势徽标。挂件单跑模式（`--widget bar|pet`）也自行驱动 `pump_edges`，不依赖主窗口。
4. 采集状态可视化：底栏"按键功能已连接/未连接（缺辅助功能权限）"，权限页给出跳转按钮。
5. 产品图使用 ZOL 商品页真实图（白底转透明，`assets/headset-ui.png`），不再用生成图。

约束未变：不拦截系统 AVRCP 行为（P0-3 方案 A），`mute:click` 仍只在 HFP 通话中上报。
