# runtime-ops — 进程生命周期与运行环境

## Purpose

定义单进程程序的运行期约束：单实例、信号处理与资源清理、配置外部变更、运行环境自检。
这些不属于业务能力，但直接决定"用户会不会用错流程把程序弄坏"。

## Requirements

### Requirement: 单实例

程序 SHALL 保证同一时间只有一个实例在运行。

#### Scenario: 重复启动
- **WHEN** 已有一个实例在运行，用户再次启动程序
- **THEN** 第二个实例立即退出，输出 `> ERR already running (pid=<pid>)，如需重启请先退出原实例`，退出码非 0

#### Scenario: 锁文件残留
- **WHEN** 锁文件中记录的 PID 已不存在（上次异常退出）
- **THEN** 视为陈旧锁，自动接管并继续启动，不阻塞用户

#### Scenario: 锁位置
- **WHEN** 程序启动
- **THEN** 锁文件位于 `$XDG_RUNTIME_DIR/clearcall200.lock`，无该变量时退化为 `/tmp/clearcall200.lock`

### Requirement: 信号与退出清理

程序 SHALL 在退出时释放所有独占资源。

#### Scenario: quit 命令
- **WHEN** 用户输入 `quit`
- **THEN** 按顺序执行：停采集 → 停推流（`ptt_state=0`）→ 关闭 `uinput` → 写回终端状态 → 删除锁文件 → 退出；若 `dirty=true` 提示未保存

#### Scenario: SIGTERM / SIGINT
- **WHEN** 进程收到 SIGTERM 或 SIGINT
- **THEN** 走与 `quit` 相同的清理路径，退出码 0；不得留下挂着的虚拟麦或锁文件

#### Scenario: uinput 释放
- **WHEN** 程序创建过虚拟 HID 设备
- **THEN** 退出时必须销毁该设备，避免系统中残留"幽灵键盘"

### Requirement: 配置外部变更

程序 SHALL 检测配置文件被外部修改，并由用户决定是否生效。

#### Scenario: 检测到变更
- **WHEN** `config/rules.json` 的 mtime 变化且与内存内容不同
- **THEN** 界面提示 `> config changed externally, 输入 reload 生效`；不自动覆盖、不静默重载

#### Scenario: 内存有未保存改动
- **WHEN** `dirty=true` 且用户输入 `reload`
- **THEN** 要求二次确认（`reload force` 覆盖，或 `save` 先保存），避免丢失用户改动

### Requirement: 运行环境自检（doctor 能力）

程序 SHALL 提供可编程的自检能力，逐项给出结论与修复建议。

#### Scenario: 检查项
- **WHEN** 执行 `doctor`
- **THEN** 至少覆盖以下检查项，逐项输出 ✅/❌ + 建议：

```
[1] bluetooth service           systemctl status bluetooth
[2] adapter present             hciconfig -a
[3] target device online        按 MAC 匹配 bluetoothctl info
[4] hfp/avrcp reachable         D-Bus MediaControl1 / HFP 节点
[5] /dev/uinput writable        权限与 udev 规则
[6] virtual mic device           PulseAudio/PipeWire 输入设备
[7] obs websocket               ws://host:port 可连
[8] busylight capable           能力探测结果（未知 / 支持 / 不支持）
[9] single instance lock        锁文件状态
```

#### Scenario: 非致命项
- **WHEN** 某项检查失败但不影响主功能（如 OBS 未启动）
- **THEN** 标记 ⚠️ 并说明"不影响基础功能"，不视为错误

#### Scenario: 致命项
- **WHEN** 蓝牙服务或适配器缺失
- **THEN** 标记 ❌ 并说明"仅可用 test 命令调试界面"，程序仍可运行

### Requirement: 权限依赖说明

程序 SHALL 在文档中明确运行所需权限，并在缺失时给出可执行命令。

#### Scenario: uinput 权限缺失
- **WHEN** 当前用户无 `/dev/uinput` 写权限
- **THEN** `doctor` 输出建议：创建 udev 规则或把用户加入 `input` 组；`hid_send` 动作返回 `> ERR uinput permission denied`
