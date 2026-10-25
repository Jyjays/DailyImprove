"""验证隐藏进程的正常退出和主程序异常退出；不启动真实服务或浏览器。"""
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from scripts.start_study import ManagedProcesses, wait_ready


@unittest.skipUnless(sys.platform == "win32", "Windows launcher")
class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="study launcher ")
        self.root = Path(self.tmp.name)
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        self.api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.api.OpenProcess.restype = wintypes.HANDLE
        self.api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.api.WaitForSingleObject.restype = wintypes.DWORD
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handles = []

    def tearDown(self):
        for handle in self.handles:
            self.api.CloseHandle(handle)
        self.tmp.cleanup()

    def handle(self, pid):
        handle = self.api.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
        self.assertTrue(handle)
        self.handles.append(handle)
        return handle

    def read_pid(self, path):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                return json.loads(path.read_text())
            except (OSError, ValueError):
                time.sleep(0.05)
        self.fail("Child process did not start")

    def test_close_stops_child_and_grandchild(self):
        managed = ManagedProcesses()
        pid_file = self.root / "child.json"
        code = ("import json,subprocess,sys,time; from pathlib import Path; "
                "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],creationflags=subprocess.CREATE_NO_WINDOW); "
                f"Path({str(pid_file)!r}).write_text(json.dumps(p.pid)); time.sleep(60)")
        try:
            child = managed.start("test", [sys.executable, "-c", code], self.root, self.root / "output.log")
            child_handle = self.handle(child.pid)
            grandchild_handle = self.handle(self.read_pid(pid_file))
            managed.close()
            self.assertEqual(self.api.WaitForSingleObject(child_handle, 5000), 0)
            self.assertEqual(self.api.WaitForSingleObject(grandchild_handle, 5000), 0)
        finally:
            managed.close()

    def test_supervisor_death_stops_its_hidden_service(self):
        pid_file = self.root / "service.json"
        repo = Path(__file__).resolve().parents[1]
        code = (f"import sys,time; sys.path.insert(0,{str(repo)!r}); from pathlib import Path; "
                "from scripts.start_study import ManagedProcesses; "
                f"m=ManagedProcesses(); p=m.start('test',[sys.executable,'-c','import time; time.sleep(60)'],Path({str(self.root)!r}),Path({str(self.root / 'service.log')!r})); "
                f"Path({str(pid_file)!r}).write_text(str(p.pid)); time.sleep(60)")
        supervisor = subprocess.Popen([sys._base_executable, "-c", code], creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            child_handle = self.handle(self.read_pid(pid_file))
            supervisor.kill()
            supervisor.wait(timeout=5)
            self.assertEqual(self.api.WaitForSingleObject(child_handle, 5000), 0)
        finally:
            if supervisor.poll() is None:
                supervisor.kill()
                supervisor.wait(timeout=5)

    def test_failed_service_prevents_false_ready(self):
        services = Mock()
        services.check_running.side_effect = RuntimeError("service exited")
        with patch("scripts.start_study.build_opener") as opener:
            with self.assertRaisesRegex(RuntimeError, "service exited"):
                wait_ready("http://127.0.0.1:4173", services)
            opener.return_value.open.assert_not_called()


if __name__ == "__main__":
    unittest.main()
