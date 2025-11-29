"""USB AutoLocker 主程序入口"""
import sys
import os
import time
import threading
import subprocess
import ctypes
import tkinter as tk
from pynput import keyboard
import win32event
import win32api
import winerror
import customtkinter as ctk

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(__file__))

from config import ConfigManager
from usb_monitor import USBMonitor
from gui.settings_window import SettingsWindow
from gui.tray_icon import TrayIconManager
from gui.countdown_popup import CountdownPopup


def check_single_instance(mutex_name="USB_AutoLocker_Mutex"):
    """确保单实例运行"""
    handle = win32event.CreateMutex(None, False, mutex_name)
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        ctypes.windll.user32.MessageBoxW(0, "USB AutoLocker 已经在运行中！", "提示", 0x40)
        sys.exit(0)
    return handle


# DPI 感知
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


class USBAutoLockerApp:
    """主应用程序类"""

    def __init__(self):
        self.config_manager = ConfigManager()
        self.usb_monitor = USBMonitor(self.config_manager)
        
        self.root: tk.Tk = None
        self.tray_manager: TrayIconManager = None
        self.countdown_popup: CountdownPopup = None
        self.settings_window: SettingsWindow = None
        
        self.is_enabled = True
        self.last_shift_time = 0
        self.popup_lock = threading.Lock()

        # 键盘监听
        self.keyboard_listener = keyboard.Listener(on_release=self._on_key_release)
        self.keyboard_listener.start()

    def _on_key_release(self, key):
        """键盘释放事件处理"""
        if not self.countdown_popup or not self.countdown_popup.is_showing:
            return

        if key in (keyboard.Key.shift_l, keyboard.Key.shift_r):
            current_time = time.time()
            if current_time - self.last_shift_time < 0.5:
                self.countdown_popup.cancel()
            self.last_shift_time = current_time

    def _execute_lock(self):
        """执行锁屏"""
        print("执行锁屏...")
        subprocess.run("rundll32.exe user32.dll,LockWorkStation", shell=True)

    def _on_device_removed(self):
        """设备拔出回调"""
        if not self.is_enabled:
            print("设备拔出，但功能已禁用")
            return

        if self.popup_lock.locked():
            return

        with self.popup_lock:
            countdown = self.config_manager.config.countdown_seconds
            self.countdown_popup = CountdownPopup(
                self.root,
                countdown,
                on_complete=self._execute_lock
            )
            self.root.after(0, self.countdown_popup.show)

    def _on_device_inserted(self):
        """设备插入回调"""
        if self.tray_manager:
            self.tray_manager.notify("USB 密钥已插入", "设备状态")

    def _toggle_enable(self):
        """切换启用状态"""
        self.is_enabled = not self.is_enabled
        self.config_manager.update(enabled=self.is_enabled)
        
        state = "已启用" if self.is_enabled else "已禁用"
        if self.tray_manager:
            self.tray_manager.notify(f"自动锁屏功能{state}", "状态更新")

    def _open_settings(self):
        """打开设置窗口"""
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.focus()
            return

        def on_save():
            # 配置保存后重启监控
            self.usb_monitor.restart()
            if self.tray_manager:
                self.tray_manager.notify("配置已保存", "设置")

        self.root.after(0, lambda: self._create_settings_window(on_save))

    def _create_settings_window(self, on_save):
        """在主线程创建设置窗口"""
        self.settings_window = SettingsWindow(
            self.root,
            self.config_manager,
            on_save=on_save
        )

    def _quit_app(self):
        """退出应用"""
        self.usb_monitor.stop()
        if self.tray_manager:
            self.tray_manager.stop()
        if self.root:
            self.root.quit()
        os._exit(0)

    def run(self):
        """运行应用"""
        # 创建 Tk 根窗口
        self.root = tk.Tk()
        self.root.withdraw()

        # 加载配置
        self.is_enabled = self.config_manager.config.enabled

        # 设置 USB 监控回调
        self.usb_monitor.on_device_removed = self._on_device_removed
        self.usb_monitor.on_device_inserted = self._on_device_inserted
        self.usb_monitor.start()

        # 创建托盘图标
        self.tray_manager = TrayIconManager(
            on_toggle_enable=self._toggle_enable,
            on_open_settings=self._open_settings,
            on_quit=self._quit_app,
            is_enabled_getter=lambda: self.is_enabled
        )
        tray_icon = self.tray_manager.create()
        
        # 在独立线程运行托盘
        threading.Thread(target=tray_icon.run, daemon=True).start()

        # 主循环
        self.root.mainloop()


if __name__ == "__main__":
    mutex = check_single_instance()
    app = USBAutoLockerApp()
    app.run()
