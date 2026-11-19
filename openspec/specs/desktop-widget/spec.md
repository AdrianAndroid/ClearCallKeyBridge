# desktop-widget — 常驻桌面挂件（键位浮条 / 桌宠）

## Purpose

把程序从"纯终端"扩展出一个**常驻、可拖动的小挂件**，解决一个问题：
用户在实际通话中不想盯着终端，但需要**即时视觉反馈**——按下某个键时，对应键位亮一下，
并显示这次被识别成什么手势（单击 / 长按 / 双击），以及通话、静音、PTT 的当前状态。

挂件是**状态镜像 + 反馈器**，不是配置界面：不承载复杂配置，不改变规则引擎的行为。

## Requirements

### Requirement: 两种形态

挂件 SHALL 支持两种形态，通过启动参数选择，且同一时间只显示一种。
两种形态都是**极小的浮层**，不是把整个程序界面搬到桌面上。

#### Scenario: 键位工具条（bar，默认）
- **WHEN** 以 `--widget bar` 启动
- **THEN** 显示一条单行工具条，默认尺寸 **320×46 px**（允许在配置中微调），只包含：
  连接指示点、通话状态缩写、4 个键位胶囊（静 / 话 / ＋ / －）、最近一次识别结果、PTT 细进度条

#### Scenario: 桌宠（pet）
- **WHEN** 以 `--widget pet` 启动
- **THEN** 显示一个不超过 **88×88 px** 的角色浮层，用表情与一两字气泡反映状态与最近一次按键

#### Scenario: 只选其一
- **WHEN** 同时传入两种形态
- **THEN** 只启动参数中第一个，并输出提示，不叠加两个窗口

#### Scenario: 尺寸纪律
- **WHEN** 渲染工具条
- **THEN** 高度不得超过 56px、宽度不得超过 420px；不得出现多行文本块、状态栏整行、日志面板等"大界面"元素

### Requirement: 常驻与窗口层级

挂件 SHALL 常驻、使用普通窗口层级、可拖动、不抢焦点。

#### Scenario: 切换应用
- **WHEN** 用户切换到其他应用窗口
- **THEN** 挂件不得强制置顶，允许被其他窗口遮挡

#### Scenario: 拖动
- **WHEN** 用户在挂件空白区域按住并拖动
- **THEN** 窗口跟随移动，位置在本进程内保持

#### Scenario: 不抢焦点
- **WHEN** 用户在挂件上点击或挂件被激活
- **THEN** 不得抢占当前前台应用的键盘焦点；挂件内不放输入框

#### Scenario: 全屏应用的平台限制
- **WHEN** 前台是 macOS 全屏应用
- **THEN** 允许挂件被全屏空间遮挡（Tk 层级的系统限制），文档与界面上不得声称"可覆盖全屏"

### Requirement: 不遮挡工作区

工具条 SHALL 默认停靠在屏幕右上角，且不自动扩展尺寸。

#### Scenario: 初始位置
- **WHEN** 首次启动
- **THEN** 位于主屏右上角（距右边距 24px、距顶部 48px），不居中、不全屏

#### Scenario: 内容溢出
- **WHEN** 识别结果文字过长
- **THEN** 截断为短标签（如 `话:长按`），不得让窗口自动变宽或换行增高

### Requirement: 按键点亮反馈

键位块 SHALL 在按下/松开边沿时改变外观，形成"亮一下"的效果。

#### Scenario: 按下点亮
- **WHEN** 收到 `edge press key=call`
- **THEN** call 键位块立即切换到高亮态（高对比背景 + 描边），并保持到松开

#### Scenario: 松开熄灭
- **WHEN** 收到 `edge release key=call`
- **THEN** 该键位块在不超过 250ms 内回到常态，避免突兀闪烁

#### Scenario: 断连补发释放
- **WHEN** 设备断连且某键处于按下态
- **THEN** 该键位块立即熄灭，不得卡在高亮

### Requirement: 手势识别结果展示

识别出 trigger 后，挂件 SHALL 在该键位附着一次短时徽标，说明识别成了什么。

#### Scenario: 徽标内容
- **WHEN** 识别到以下 trigger
- **THEN** 徽标文字分别为：

```
mute:click  → 静音
call:click  → 单击
call:long   → 长按
call:double → 双击
volp:click  → 音量+
volp:long   → 长按
volm:click  → 音量−
```

#### Scenario: 徽标消退
- **WHEN** 徽标显示后 1.2 秒内没有新的同键事件
- **THEN** 徽标淡出消失；新事件到来时重置计时

#### Scenario: 未绑定动作
- **WHEN** 某 trigger 的 action 为 `none`
- **THEN** 仍然点亮并显示徽标（用户需要知道"键通了、只是没绑动作"），但不得显示动作名

### Requirement: 状态镜像

挂件 SHALL 与终端界面共用同一份状态源，显示口径一致。

#### Scenario: 通话状态
- **WHEN** `call_state` 变化
- **THEN** 挂件状态条同步更新：idle 灰、ringing 琥珀（闪烁）、active 绿、held 蓝、dialing 蓝

#### Scenario: 麦克风
- **WHEN** `mic_mute` 变化
- **THEN** 显示 `MIC ON` / `MIC MUTED`，静音态用琥珀色

#### Scenario: 学习模式
- **WHEN** `app_mode=learn`
- **THEN** 挂件边框或提示变为琥珀色，并显示"只检测不执行"，与终端提示口径一致

### Requirement: PTT 进度

挂件 SHALL 在推流期间给出进度/持续时长反馈。

#### Scenario: hold 模式
- **WHEN** `ptt_state=1` 且 `ptt_mode=hold`
- **THEN** 显示一条进度条，长度随按住时长增长，上限为 `ptt_hold_max_sec`；并显示已按住秒数

#### Scenario: toggle 模式
- **WHEN** `ptt_state=1` 且 `ptt_mode=toggle`
- **THEN** 显示 `PTT ON` 脉冲提示（不做进度条，因为没有自动结束点）

#### Scenario: 停止
- **WHEN** `ptt_state` 回到 0
- **THEN** 进度条立即清零并隐藏

### Requirement: 与主程序协同

挂件 SHALL 与规则、采集、动作执行同进程协作，不得另起一套逻辑。

#### Scenario: 单进程
- **WHEN** 以挂件形态启动
- **THEN** 采集 / 规则 / 动作 / 学习模式倒计时仍由同一个 App 实例驱动，不额外起第二个进程

#### Scenario: 学习模式零动作
- **WHEN** 挂件处于学习模式
- **THEN** 挂件只做点亮与徽标，**不得触发任何动作执行**（与 learn-mode spec 一致）

#### Scenario: 退出
- **WHEN** 用户关闭挂件窗口
- **THEN** 走统一清理路径（停推流、释放锁），进程正常退出

### Requirement: 主设置窗口

除挂件外，程序 SHALL 提供主设置窗口，承担"自定义按键"这件事本身；
挂件只负责保活与反馈，不承担配置。

#### Scenario: 规则编辑
- **WHEN** 打开主设置窗口
- **THEN** 7 个触发源逐行列出：序号、触发源名、动作下拉（`none` / `ptt_toggle` / `ptt_hold` / `hid_send` / `obs_toggle_mute` / `notify`）、参数输入框、测试按钮
- **THEN** 参数输入框仅在 `hid_send`（填按键名，如 `F13`）与 `notify`（填文本）时启用，其余动作置灰

#### Scenario: 编辑走既有校验
- **WHEN** 用户修改某行并点"应用"
- **THEN** GUI 通过既有命令路径提交（等价于 `set N ACTION`），非法动作由 `rules.py` 拒绝并原样保留旧值，错误以 `ERR` 行显示
- **WHEN** 点"保存"
- **THEN** 等价于执行 `save`，落盘 `config/rules.json`

#### Scenario: 参数编辑
- **WHEN** 用户修改 `long_press_ms` / `double_click_ms` / `learn_timeout_sec` / `ptt_hold_max_sec` / `actions.ptt.source`
- **THEN** 校验为正整数（超时类 ≥1 秒），非法输入标红提示且不写入

#### Scenario: 单测/试按
- **WHEN** 点击某行"测试"
- **THEN** 注入一次该触发源的识别（`app._handle_trigger`），挂件同步点亮，事件流出现 `EVENT trigger=...`
- **THEN** 学习模式下只走检测分支，不执行动作

#### Scenario: 学习模式入口
- **WHEN** 点击"学习模式"/"正常"
- **THEN** 与命令 `learn` / `normal` 行为一致，挂件边框同步转琥珀/恢复

#### Scenario: 关闭主窗口不退出程序
- **WHEN** 用户关闭主设置窗口
- **THEN** 只隐藏主窗口，**进程继续常驻**，挂件保持显示（这是"保活"语义）
- **WHEN** 用户关闭挂件
- **THEN** 才执行统一清理并退出进程

#### Scenario: 单一 Tk 主循环
- **WHEN** 主窗口与挂件同时存在
- **THEN** 二者共用一个 Tk root（挂件是 Toplevel），不得起第二个 `Tk()` 实例
