"""Windows 单控制台启动器；隐藏子进程，主控制台关闭时清理整个服务进程树。"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener


ROOT = Path(__file__).resolve().parents[1]


class WindowsJob:
    """所有后台进程都加入同一 Job；主进程退出使句柄关闭并终止子孙进程。"""

    def __init__(self):
        if sys.platform != "win32":
            raise RuntimeError("此启动器用于 Windows，请在其他系统使用 start.sh。")

        class BasicLimits(ctypes.Structure):
            _fields_ = [("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
                        ("flags", wintypes.DWORD), ("min_working_set", ctypes.c_size_t),
                        ("max_working_set", ctypes.c_size_t), ("active_processes", wintypes.DWORD),
                        ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD), ("scheduling", wintypes.DWORD)]

        class IOCounters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in
                        ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [("basic", BasicLimits), ("io", IOCounters), ("process_memory", ctypes.c_size_t),
                        ("job_memory", ctypes.c_size_t), ("peak_process_memory", ctypes.c_size_t),
                        ("peak_job_memory", ctypes.c_size_t)]

        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        self.api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.api.CreateJobObjectW.restype = wintypes.HANDLE
        self.api.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self.api.SetInformationJobObject.restype = wintypes.BOOL
        self.api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.api.AssignProcessToJobObject.restype = wintypes.BOOL
        self.api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.api.OpenProcess.restype = wintypes.HANDLE
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.api.CloseHandle.restype = wintypes.BOOL
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def assign(self, process: subprocess.Popen):
        handle = self.api.OpenProcess(0x0100 | 0x0001, False, process.pid)  # SET_QUOTA | TERMINATE
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not self.api.AssignProcessToJobObject(self.handle, handle):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            self.api.CloseHandle(handle)

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


class ManagedProcesses:
    def __init__(self):
        self.job = WindowsJob()
        self.services: list[tuple[str, subprocess.Popen, Path]] = []

    def start(self, name: str, command: list[str], cwd: Path, log_path: Path):
        log_path.parent.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, NO_PROXY="127.0.0.1,localhost", no_proxy="127.0.0.1,localhost",
                   PYTHONUNBUFFERED="1", PYTHONUTF8="1")
        with log_path.open("ab") as log:
            log.write(f"\n--- {datetime.now().isoformat(timespec='seconds')} ---\n".encode("utf-8"))
            log.flush()
            process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=subprocess.STDOUT,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            self.job.assign(process)
        except OSError:
            process.kill()
            process.wait()
            raise
        self.services.append((name, process, log_path))
        return process

    def check_running(self):
        for name, process, log_path in self.services:
            if process.poll() is not None:
                raise RuntimeError(f"{name}已退出（退出码 {process.returncode}）。请查看日志：{log_path}")

    def close(self):
        self.job.close()
        for _, process, _ in self.services:
            process.wait(timeout=10)


def check_port(port: int):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            raise RuntimeError(f"端口 {port} 已被占用，请先退出已有学习台或占用此端口的程序。") from None


def wait_ready(url: str, services: ManagedProcesses, timeout: float = 60):
    opener = build_opener(ProxyHandler({}))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        services.check_running()
        try:
            with opener.open(url, timeout=1) as response:
                if response.status == 200:
                    return
        except (OSError, URLError):
            pass
        time.sleep(0.2)
    raise RuntimeError(f"等待服务就绪超时：{url}。请查看 data/logs 下的启动日志。")


def run(open_browser: bool = True) -> int:
    services = None
    try:
        node = shutil.which("node")
        web = ROOT / "test1" / "test1"
        vite = web / "node_modules" / "vite" / "bin" / "vite.js"
        if not node:
            raise RuntimeError("未找到 Node.js，请先安装 Node.js。")
        if not vite.is_file():
            raise RuntimeError(f"前端依赖未安装，请在 {web} 执行 npm install。")
        for port in (8000, 4173):
            check_port(port)
        services = ManagedProcesses()
        print("[1/2] 正在后台启动后端…", flush=True)
        services.start("后端", [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
                       ROOT, ROOT / "data/logs/backend.log")
        wait_ready("http://127.0.0.1:8000/api/status", services)
        print("[2/2] 正在后台启动前端…", flush=True)
        services.start("前端", [node, str(vite), "--host", "127.0.0.1", "--port", "4173", "--strictPort"],
                       web, ROOT / "data/logs/frontend.log")
        wait_ready("http://127.0.0.1:4173", services)
        print("\n学习台已启动：http://127.0.0.1:4173")
        print(f"后台日志：{ROOT / 'data/logs'}")
        print("按回车或 Q 统一退出；关闭此主窗口也会结束本次启动的后台服务。", flush=True)
        if open_browser:
            try:
                os.startfile("http://127.0.0.1:4173")
            except OSError:
                print("浏览器未能自动打开，请手动访问上方地址。", flush=True)
        import msvcrt
        while True:
            services.check_running()
            if msvcrt.kbhit() and msvcrt.getwch().lower() in ("\r", "q"):
                break
            time.sleep(0.2)
        return 0
    except KeyboardInterrupt:
        return 0
    except (OSError, RuntimeError) as error:
        print(f"\n[错误] {error}", flush=True)
        return 1
    finally:
        if services is not None:
            print("\n正在停止后台服务…", flush=True)
            services.close()
            print("前后端已停止。", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DailyImprove 单控制台启动器")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args()
    raise SystemExit(run(open_browser=not args.no_browser))
