"""进程生命周期：单实例锁、退出清理、日志落盘、信号处理。

规范：openspec/specs/runtime-ops/spec.md
"""
from __future__ import annotations

import os
import signal
import sys
from pathlib import Path


def lock_path() -> Path:
    """锁文件的规范位置：$XDG_RUNTIME_DIR 优先，退化为 /tmp。"""
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir and Path(runtime_dir).is_dir():
        return Path(runtime_dir) / "clearcall200.lock"
    return Path("/tmp/clearcall200.lock")


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


class Runtime:
    def __init__(self, log_path: str | None = None):
        self._lock_file = lock_path()
        self._locked = False
        self.stop_requested = False
        self._log_path = Path(log_path) if log_path else None
        self.log_error: str | None = None

    # ---- 单实例 ----
    def acquire_lock(self) -> tuple[bool, str]:
        """返回 (是否拿到锁, 说明)。陈旧锁会被自动接管。"""
        try:
            if self._lock_file.exists():
                content = self._lock_file.read_text(encoding="utf-8").strip()
                pid_text = content.split()[0] if content else ""
                pid = int(pid_text) if pid_text.isdigit() else 0
                if pid and pid != os.getpid() and _pid_alive(pid):
                    return False, f"already running (pid={pid})，如需重启请先退出原实例"
                # 陈旧锁：接管
            self._lock_file.parent.mkdir(parents=True, exist_ok=True)
            self._lock_file.write_text(str(os.getpid()), encoding="utf-8")
            self._locked = True
            return True, f"lock acquired: {self._lock_file}"
        except Exception as exc:  # 锁失败不应阻止程序运行
            return True, f"lock skipped: {exc}"

    def release_lock(self) -> None:
        if not self._locked:
            return
        try:
            if self._lock_file.exists():
                if self._lock_file.read_text(encoding="utf-8").strip() == str(os.getpid()):
                    self._lock_file.unlink()
        except Exception:
            pass
        self._locked = False

    # ---- 日志落盘 ----
    def attach_log(self) -> str | None:
        """把事件流写到 --log 指定的文件；失败时返回错误信息。"""
        if not self._log_path:
            return None
        try:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            # 启动时新建/覆盖，避免把历史日志混进来
            self._log_path.write_text("", encoding="utf-8")
            return None
        except Exception as exc:
            self.log_error = str(exc)
            self._log_path = None
            return str(exc)

    def write_log(self, line: str) -> None:
        if not self._log_path:
            return
        try:
            with self._log_path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except Exception as exc:
            self.log_error = str(exc)
            self._log_path = None  # 写失败就停用，不影响主流程

    # ---- 信号 ----
    def install_signals(self) -> None:
        def handler(signum, _frame):  # noqa: ANN001
            self.stop_requested = True

        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(sig, handler)
            except Exception:
                pass  # 非主线程或无权限时忽略

    def exit_now(self, code: int = 0) -> None:
        try:
            sys.stdout.write("\n")
            sys.stdout.flush()
        except Exception:
            pass
        raise SystemExit(code)
