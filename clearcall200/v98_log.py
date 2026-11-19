"""V98 只读日志检测通道。

实测依据（docs/V98按键监听交接.md）：普通权限（无提升、无诊断描述文件）下，
`/usr/bin/log stream` 按 bluetoothd + 目标地址过滤可实时读到两类消息：

    Received AVRCP Play command from device 41:42:DF:39:9A:BE
    Received notification for absolute volume 0x1c (~22%) from device ...

约束（openspec/changes/2026-11-19-v98-log-detect.md）：
- 只读旁听，不是拦截；系统对同一命令的处理照常发生。
- 解析层按地址二次过滤，只处理上述两类消息，其他行一律忽略。
- 日志没有可靠 release，禁止据此伪造边沿或支持 ptt_hold。
- 音量通知存在同值重复 / 多值交错，不做方向判定，只如实展示。
"""
from __future__ import annotations

import queue
import re
import subprocess
import threading

LOG_BIN = "/usr/bin/log"

_MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")

# 只有实测验证过的两类消息会产出检测事件
_PLAY_RE = re.compile(
    r"Received AVRCP Play command from device "
    r"(?P<addr>[0-9A-Fa-f:]{17})",
    re.IGNORECASE,
)
_PAUSE_RE = re.compile(
    r"Received AVRCP Pause command from device "
    r"(?P<addr>[0-9A-Fa-f:]{17})",
    re.IGNORECASE,
)
_VOL_RE = re.compile(
    r"Received notification for absolute volume "
    r"(?P<val>0x[0-9a-fA-F]+)\s+\(~(?P<pct>\d+)%\)\s+from device "
    r"(?P<addr>[0-9A-Fa-f:]{17})",
    re.IGNORECASE,
)


def valid_address(addr: object) -> bool:
    """地址必须是冒号分隔的 6 字节形式，不允许占位符糊弄过校验。"""
    return isinstance(addr, str) and bool(_MAC_RE.match(addr))


def parse_log_line(line: str, target: str) -> tuple | None:
    """解析一行 bluetoothd 日志 → 检测事件；不匹配或不属于目标地址返回 None。

    事件形态：
      ("play",)
      ("pause",)
      ("volume", "0x28", 31)
    纯函数，供子进程线程与单测共用。
    """
    if not line or target.upper() not in line.upper():
        return None
    m = _PLAY_RE.search(line)
    if m and m.group("addr").upper() == target.upper():
        return ("play",)
    m = _PAUSE_RE.search(line)
    if m and m.group("addr").upper() == target.upper():
        return ("pause",)
    m = _VOL_RE.search(line)
    if m and m.group("addr").upper() == target.upper():
        return ("volume", m.group("val").lower(), int(m.group("pct")))
    return None


def build_predicate(target: str) -> str:
    """构造 log stream 谓词：按进程 + 地址过滤（内容过滤交给解析层二次防线）。"""
    return (
        f'process == "bluetoothd" AND '
        f'composedMessage CONTAINS[c] "{target}"'
    )


class V98LogWatcher:
    """异步启动 log stream 子进程，逐行解析后进队列。

    状态机：disabled / starting / running / unavailable:<reason>
    使用方先 attach（start），随后在自己的 UI 循环里 pump 队列，退出时 stop()。
    """

    def __init__(self, address: str, queue_size: int = 128):
        self.address = address.upper()
        self.q: queue.Queue = queue.Queue(maxsize=queue_size)
        self.status = "disabled"
        self._proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None

    # ---------------- 生命周期 ----------------
    def start(self) -> str:
        """启动子进程与读线程；返回最终状态（成功为 running）。"""
        if self.status in ("starting", "running"):
            return self.status
        if not valid_address(self.address):
            self.status = "unavailable:address not configured"
            return self.status
        try:
            self._proc = subprocess.Popen(
                [
                    LOG_BIN, "stream", "--style", "compact",
                    "--level", "default",
                    "--predicate", build_predicate(self.address),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                errors="ignore",
                bufsize=1,
            )
        except OSError as exc:
            self.status = f"unavailable:{exc.__class__.__name__}"
            return self.status

        self.status = "starting"
        self._thread = threading.Thread(
            target=self._reader, name="v98-log-watcher", daemon=True)
        self._thread.start()
        return self.status

    def stop(self) -> None:
        """终止子进程并回收线程；退出路径必须调用，不阻塞调用方。"""
        proc, self._proc = self._proc, None
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    proc.kill()
            except Exception:
                pass
        thread, self._thread = self._thread, None
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)
        if self.status in ("starting", "running"):
            self.status = "disabled"

    # ---------------- 内部 ----------------
    def _reader(self) -> None:
        """后台线程：读子进程 stdout，解析后入队（队列满时丢旧保新）。"""
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        try:
            for line in proc.stdout:
                ev = parse_log_line(line.rstrip("\n"), self.address)
                if ev is None:
                    continue
                try:
                    self.q.put_nowait(ev)
                except queue.Full:
                    try:
                        self.q.get_nowait()
                    except queue.Empty:
                        pass
                    try:
                        self.q.put_nowait(ev)
                    except queue.Full:
                        pass
                if self.status != "running":
                    self.status = "running"
        finally:
            code = proc.wait(timeout=1.0)
            # 只有仍在运行态才覆盖为 unavailable（stop() 期间保持 disabled）
            if self.status in ("starting", "running"):
                self.status = f"unavailable:stream exited ({code})"

    # ---------------- 供 UI 循环 ----------------
    def drain(self) -> list[tuple]:
        """取出全部待处理检测事件（非阻塞，主线程调用）。"""
        out = []
        while True:
            try:
                out.append(self.q.get_nowait())
            except queue.Empty:
                break
        return out
