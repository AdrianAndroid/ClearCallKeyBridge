# CLAUDE.md — 项目强约束（AI 开发助手必须先读）

> 本文件与 `.cursorrules` 内容一致，供编码 AI 自动读取，避免每次重复粘贴长提示词。
> 任何与 `openspec/` 冲突的实现都算 bug；要改行为，先改 spec，再改代码。

## 1. 项目定位（最容易跑偏的地方，务必遵守）

- 目标产品：漫步者 **ClearCall 200** 头戴话务耳机按键自定义客户端。
- **程序是单体、单进程、本地运行的终端程序**：蓝牙采集、按键解析、规则管理、状态机、动作执行、ASCII 界面全在同一个程序内。
- **OpenSpec 只是模型/契约规范文档**（`openspec/` 目录），是设计标准，**不是运行中的服务**。
- ❌ 禁止实现「OpenSpec 独立服务 / TCP 中枢 / Agent-Worker 分布式架构」。那是以后的事，MVP 不做。
- 参考体验：`remote-mic-app`（PTT 按住说话 + 按键自定义映射），我们额外叠加 HFP 通话状态显示。

## 2. 目标平台

- 首选 **Linux（BlueZ / btmon）**，开发调试环境。
- 预留 macOS 适配入口（IOBluetooth / 抓包解析），但 MVP 不实现。
- 蓝牙采集、UI 渲染、定时器必须解耦，UI 不能阻塞采集循环。

## 3. 触发源（固定 7 条事件，来自 4 个物理按键）

```
mute:click     静音键单击     — 仅 HFP 通话 active 时耳机才上报；空闲按大概率无报文（硬件限制，不要伪造）
call:click     通话键单击
call:long      通话键长按
call:double    通话键双击
volp:click     音量+ 单击
volp:long      音量+ 长按     — AVRCP，最稳定
volm:click     音量- 单击
```

- `power` 电源键：**不加入触发列表**，只作链路生命周期。
- 长按阈值、双击间隔阈值必须可配置（默认长按 ≥ 1.5s，双击间隔 ≤ 500ms），并做防抖。

## 4. 状态模型

```
app_mode  : normal | learn
call_state: idle | ringing | active | held | dialing
mic_mute  : 0 = 麦开启 / 1 = 麦静音
ptt_state : 0 = 关闭   / 1 = 开启
ptt_mode  : toggle | hold
```

## 5. 动作集合（MVP 只这 5 个，不许自行扩展）

```
ptt_toggle          切换 PTT 虚拟麦克风开关（按一下开/再按关）
ptt_hold            按住说话：press 开麦、release 停麦（对标 remote-mic-app 手感）
hid_send F13        发送 HID 键盘码（支持 F13/F14 等）
obs_toggle_mute     通过 OBS WebSocket 切换麦克风静音
notify"文本"        系统桌面通知
```

- 一条触发源只绑定**单个**动作（MVP 限制）。
- 推流必须区分 `ptt_mode`（toggle / hold），两种模式不得叠加；设备断连 / 释放丢失 / 退出时必须强制停麦。
- PTT 输入源取配置 `actions.ptt.source`（`default` / `headset`），源设备不在则报 ERR 并停麦。
- MVP **不实现**：`shell` 任意脚本、zoom/teams 静音、多动作串联、条件分支、组合按键、多套配置切换。
- 规则持久化到本地配置文件（JSON），启动自动加载，不存在则写入默认示例规则。

### 关于"拦截"的现实（P0-3 决策 A：并存）
AVRCP 音量/媒体键由 BlueZ + 音频服务直接消费，**程序能看到事件但无法阻止系统默认行为**。
因此自定义动作与原系统行为同时发生。界面与文档必须如实说明，**不得宣称"已拦截"**；
推荐把自定义优先绑到 `volp:long` / `volm:click` / `call:long`。

## 6. 运行模式

### normal
按键 → 匹配规则 → 执行动作 → 更新状态与界面。

### learn（学习/测试模式，重点功能）
- 进入后：**继续采集、继续刷新通话状态栏，但禁止执行任何绑定动作**。
- 识别成功：终端打印 `> [LEARN ✅] trigger=xxx → BusyLight blink ✨`，并尝试下发忙灯闪烁指令做物理反馈。
- 忙灯不支持：降级为 `> [LEARN ✅] trigger=xxx → BusyLight control unsupported`，不报错、不中断。
- **默认 30s 自动超时退出回 normal**；也可入力 `normal` 手动退出。
- 学习模式不是"重定义按键流程"，MVP 阶段只做检测与反馈，不写入规则。

## 7. 界面（终端为主 UI；允许 Tk 常驻挂件；禁止 Web / Electron）

终端 ASCII 界面是主界面与调试入口。另允许一个**极小的常驻置顶浮层**（`--widget bar` 320×46 键位工具条 / `--widget pet` 88×88 桌宠），只做状态镜像与按键点亮，不承载配置、不复制规则逻辑。


顶部常驻状态栏：
```
📞 CALL: [IDLE] | MIC: [OPEN] | PTT: [OFF] | MODE:[NORMAL]
```
learn 模式下增加提示行：
```
⚠️ LEARN MODE ACTIVE: 按键只会检测、不执行动作 | 30s auto exit
```
面板自上而下：状态栏 → 触发源列表（带序号 + 硬件限制备注）→ 当前规则表 → 实时事件流 → 命令提示符 `> _`

事件流格式：
```
> EVENT trigger=volp:long
> ACTION action=ptt_toggle
> STATE call_state=active mic_mute=1
> [LEARN ✅] trigger=call:click        → BusyLight blink ✨
```

## 8. 交互命令（必须全部实现）

```
list          打印当前全部规则
set N ACTION  改写第 N 号触发源的绑定动作（如 set 5 ptt_hold）
learn         进入学习/测试模式
normal        退出学习模式回到 normal
test TRIG     手动模拟触发（如 test trigger=volp:long），用于无蓝牙时调试
save          保存规则到本地配置文件
reload        重新读取配置文件（dirty 时需确认，不静默覆盖）
state         立即打印最新通话/静音/模式状态
doctor        环境自检（蓝牙/权限/uinput/虚拟麦/OBS/忙灯/实例锁）
debug on|off  开关原始报文摘要输出（默认 off）
export feed   导出最近 200 行事件流为文本
help          命令说明
quit          退出程序
```

## 9. 代码结构（按模块开发，不要堆在一个文件）

```
bluetooth/    BlueZ / btmon 采集，AVRCP + HFP 报文解析
parser/       时序解析：按下/松开 → 单击/长按/双击，防抖；输出 trigger + edge 事件
rules/        规则表加载、增删改查、持久化
state/        状态机（含 ptt_mode）+ learn 倒计时
executor/     动作执行：ptt_toggle / ptt_hold / hid / obs / notify
ui/           ASCII 终端渲染（非阻塞、增量刷新）
busylight/    忙灯能力探测与闪烁（失败自动降级）
runtime/      单实例锁、信号清理、日志落盘、配置变更检测
diag/         doctor 自检项实现
```

## 10. 交付方式

- 分模块迭代，一次只写一个模块，先说明「本次开发哪个模块」。
- 代码必须带注释；新增依赖要给出安装命令（apt / pip / cargo / npm）。
- 出现方案选择时，先列方案对比再写代码。
- 有不清楚的地方先提问，**不要自行增加需求**。
