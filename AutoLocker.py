"""
USB AutoLocker - 单文件版本
检测特定USB设备断开连接后自动锁屏，适用于Windows平台
"""
import json
import os
import re
import sys
import time
import threading
import subprocess
import ctypes
import winreg
import tkinter as tk
from dataclasses import dataclass, asdict
from typing import List, Optional, Callable

import wmi
import pythoncom
from pystray import Icon, Menu, MenuItem
from PIL import Image, ImageDraw
from pynput import keyboard
import win32event
import win32api
import winerror
import customtkinter as ctk


# ==================== 单实例检查 ====================

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


# ==================== 配置管理 ====================

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")


@dataclass
class AppConfig:
    """应用配置数据类"""
    device_vid: str = "VID_1050"
    device_pid: str = "PID_0407"
    device_name: str = ""
    countdown_seconds: int = 5
    auto_start: bool = False
    enabled: bool = True

    def get_device_id_pattern(self) -> str:
        return f"%{self.device_vid}&{self.device_pid}%"

    def get_pnp_id(self) -> str:
        return f"USB\\{self.device_vid}&{self.device_pid}"


class ConfigManager:
    """配置文件管理器"""

    def __init__(self, config_path: str = CONFIG_FILE):
        self.config_path = config_path
        self.config = self.load()

    def load(self) -> AppConfig:
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return AppConfig(**data)
            except (json.JSONDecodeError, TypeError) as e:
                print(f"配置文件读取失败，使用默认配置: {e}")
        return AppConfig()

    def save(self, config: Optional[AppConfig] = None) -> bool:
        if config:
            self.config = config
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(asdict(self.config), f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"配置保存失败: {e}")
            return False

    def update(self, **kwargs) -> None:
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
        self.save()


# ==================== USB 扫描 ====================

@dataclass
class USBDevice:
    """USB 设备信息"""
    vid: str
    pid: str
    name: str
    device_id: str

    @property
    def display_name(self) -> str:
        return f"{self.name} ({self.vid}&{self.pid})"

    @property
    def vid_pid(self) -> str:
        return f"{self.vid}&{self.pid}"


class USBScanner:
    """USB 设备扫描器"""
    VID_PID_PATTERN = re.compile(r'VID_([0-9A-Fa-f]{4})&PID_([0-9A-Fa-f]{4})', re.IGNORECASE)

    @classmethod
    def scan_devices(cls) -> List[USBDevice]:
        devices = []
        seen = set()
        try:
            c = wmi.WMI()
            for device in c.Win32_PnPEntity():
                device_id = device.DeviceID or ""
                if not device_id.startswith("USB\\"):
                    continue
                match = cls.VID_PID_PATTERN.search(device_id)
                if match:
                    vid = f"VID_{match.group(1).upper()}"
                    pid = f"PID_{match.group(2).upper()}"
                    vid_pid = f"{vid}&{pid}"
                    if vid_pid in seen:
                        continue
                    seen.add(vid_pid)
                    name = device.Name or device.Description or "未知设备"
                    devices.append(USBDevice(vid=vid, pid=pid, name=name, device_id=device_id))
        except Exception as e:
            print(f"USB 扫描失败: {e}")
        return devices

    @classmethod
    def find_device(cls, vid: str, pid: str) -> Optional[USBDevice]:
        for device in cls.scan_devices():
            if device.vid.upper() == vid.upper() and device.pid.upper() == pid.upper():
                return device
        return None


# ==================== 开机自启 ====================

APP_NAME = "USB-AutoLocker"


class AutoStartManager:
    """Windows 开机自启管理器"""
    REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"

    @classmethod
    def get_exe_path(cls) -> str:
        """获取启动命令路径"""
        if getattr(sys, 'frozen', False):
            # PyInstaller 打包后
            return f'"{sys.executable}"'
        else:
            # 开发环境：优先使用 pythonw（静默），否则用 python
            python_dir = os.path.dirname(sys.executable)
            pythonw = os.path.join(python_dir, 'pythonw.exe')
            if os.path.exists(pythonw):
                python_path = pythonw
            else:
                python_path = sys.executable
            script_path = os.path.abspath(__file__)
            return f'"{python_path}" "{script_path}"'

    @classmethod
    def get_current_path(cls) -> Optional[str]:
        """获取当前注册表中的启动路径"""
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, cls.REG_PATH, 0, winreg.KEY_READ)
            try:
                value, _ = winreg.QueryValueEx(key, APP_NAME)
                return value
            except FileNotFoundError:
                return None
            finally:
                winreg.CloseKey(key)
        except Exception:
            return None

    @classmethod
    def is_enabled(cls) -> bool:
        """检查是否已启用开机自启"""
        return cls.get_current_path() is not None

    @classmethod
    def enable(cls) -> bool:
        """启用开机自启"""
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, cls.REG_PATH, 0, winreg.KEY_SET_VALUE)
            exe_path = cls.get_exe_path()
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, exe_path)
            winreg.CloseKey(key)
            # 验证写入成功
            if cls.get_current_path() == exe_path:
                print(f"开机自启已启用: {exe_path}")
                return True
            return False
        except Exception as e:
            print(f"启用开机自启失败: {e}")
            return False

    @classmethod
    def disable(cls) -> bool:
        """禁用开机自启"""
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, cls.REG_PATH, 0, winreg.KEY_SET_VALUE)
            try:
                winreg.DeleteValue(key, APP_NAME)
                print("开机自启已禁用")
            except FileNotFoundError:
                pass  # 本来就没有
            winreg.CloseKey(key)
            return True
        except Exception as e:
            print(f"禁用开机自启失败: {e}")
            return False

    @classmethod
    def set_enabled(cls, enabled: bool) -> bool:
        """设置开机自启状态"""
        return cls.enable() if enabled else cls.disable()

    @classmethod
    def update_path_if_needed(cls) -> None:
        """如果路径变化，更新注册表（用于程序移动后）"""
        current = cls.get_current_path()
        if current is not None:
            expected = cls.get_exe_path()
            if current != expected:
                print(f"检测到路径变化，更新自启动路径...")
                cls.enable()


# ==================== USB 监控 ====================

class USBMonitor:
    """USB 设备监控器"""

    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.device_present = False
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.on_device_removed: Optional[Callable] = None
        self.on_device_inserted: Optional[Callable] = None

    def check_device_presence(self) -> bool:
        try:
            c = wmi.WMI()
            pnp_id = self.config_manager.config.get_pnp_id()
            results = c.query(f"SELECT DeviceID FROM Win32_PnPEntity WHERE DeviceID LIKE '{pnp_id}%'")
            return bool(results)
        except Exception as e:
            print(f"设备检测失败: {e}")
            return False

    def _monitor_loop(self):
        pythoncom.CoInitialize()
        try:
            c = wmi.WMI()
            device_pattern = self.config_manager.config.get_device_id_pattern()
            print(f"开始监听设备 {device_pattern}...")

            deletion_query = f"SELECT * FROM __InstanceDeletionEvent WITHIN 1 WHERE TargetInstance ISA 'Win32_PnPEntity' AND TargetInstance.DeviceID LIKE '{device_pattern}'"
            watcher_deletion = c.watch_for(raw_wql=deletion_query)

            creation_query = f"SELECT * FROM __InstanceCreationEvent WITHIN 1 WHERE TargetInstance ISA 'Win32_PnPEntity' AND TargetInstance.DeviceID LIKE '{device_pattern}'"
            watcher_creation = c.watch_for(raw_wql=creation_query)

            while self.running:
                try:
                    event = watcher_deletion(timeout_ms=100)
                    if event and self.device_present:
                        print("检测到设备拔出！")
                        self.device_present = False
                        if self.on_device_removed:
                            self.on_device_removed()
                except wmi.x_wmi_timed_out:
                    pass

                try:
                    event = watcher_creation(timeout_ms=100)
                    if event and not self.device_present:
                        print("检测到设备插入！")
                        self.device_present = True
                        if self.on_device_inserted:
                            self.on_device_inserted()
                except wmi.x_wmi_timed_out:
                    pass
                except Exception as e:
                    print(f"监听错误: {e}")
                    time.sleep(2)
        finally:
            pythoncom.CoUninitialize()

    def start(self):
        if self.running:
            return
        self.device_present = self.check_device_presence()
        print(f"初始设备状态: {'已连接' if self.device_present else '未连接'}")
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
            self.thread = None

    def restart(self):
        self.stop()
        time.sleep(0.5)
        self.start()


# ==================== 倒计时弹窗 ====================

class CountdownPopup:
    """倒计时弹窗"""

    def __init__(self, root: tk.Tk, countdown_seconds: int, on_complete: Callable, on_cancel: Optional[Callable] = None):
        self.root = root
        self.countdown_seconds = countdown_seconds
        self.on_complete = on_complete
        self.on_cancel = on_cancel
        self.popup: Optional[tk.Toplevel] = None
        self.label: Optional[tk.Label] = None
        self.remaining = countdown_seconds
        self.cancelled = False

    def _get_scale_factor(self, window) -> float:
        return window.winfo_fpixels('1i') / 96.0

    def show(self):
        self.cancelled = False
        self.remaining = self.countdown_seconds
        self.popup = tk.Toplevel(self.root)
        self.popup.attributes("-topmost", True)
        self.popup.overrideredirect(True)

        scale = self._get_scale_factor(self.popup)
        w, h = int(500 * scale), int(160 * scale)
        x = (self.popup.winfo_screenwidth() // 2) - (w // 2)
        y = (self.popup.winfo_screenheight() // 2) - (h // 2)
        self.popup.geometry(f"{w}x{h}+{x}+{y}")
        self.popup.configure(bg='#ffcccc')

        self.label = tk.Label(self.popup, text=f"！USB密钥已拔出 ！\n将在 {self.remaining} 秒后锁屏",
                              font=("Microsoft YaHei", int(16 * scale), "bold"), bg='#ffcccc', fg='red')
        self.label.pack(expand=True, pady=20)
        tk.Label(self.popup, text="连按两次 Shift 键取消",
                 font=("Microsoft YaHei", int(10 * scale), "bold"), bg='#ffcccc').pack(pady=5)
        self._tick()

    def _tick(self):
        if not self.popup:
            return
        if self.cancelled:
            self.label.config(text="！已取消锁屏 ！", fg='green')
            self.root.after(1500, self.close)
            return
        if self.remaining > 0:
            self.label.config(text=f"！USB密钥已拔出 ！\n将在 {self.remaining} 秒后锁屏")
            self.remaining -= 1
            self.root.after(1000, self._tick)
        else:
            self.close()
            self.on_complete()

    def cancel(self):
        self.cancelled = True

    def close(self):
        if self.popup:
            self.popup.destroy()
            self.popup = None

    @property
    def is_showing(self) -> bool:
        return self.popup is not None


# ==================== 托盘图标 ====================

class TrayIconManager:
    """托盘图标管理器"""

    def __init__(self, on_toggle: Callable, on_settings: Callable, on_quit: Callable, is_enabled_getter: Callable[[], bool]):
        self.on_toggle = on_toggle
        self.on_settings = on_settings
        self.on_quit = on_quit
        self.is_enabled_getter = is_enabled_getter
        self.icon: Optional[Icon] = None

    def _create_image(self, is_enabled: bool) -> Image.Image:
        image = Image.new('RGB', (64, 64), color=(255, 255, 255))
        dc = ImageDraw.Draw(image)
        dc.rectangle((15, 28, 50, 51), outline="black", fill="black")
        dc.line((23, 22, 23, 28), fill="black", width=4)
        if is_enabled:
            dc.arc((22, 12, 42, 36), start=180, end=0, fill="black", width=4)
            dc.line((40, 22, 40, 28), fill="black", width=4)
        else:
            dc.arc((22, 12, 42, 36), start=180, end=300, fill="black", width=4)
        return image

    def create(self) -> Icon:
        menu = Menu(
            MenuItem('启用自动锁屏', lambda i, item: (self.on_toggle(), self.update_icon()), checked=lambda item: self.is_enabled_getter()),
            MenuItem('设置', lambda i, item: self.on_settings(), default=True),  # 双击默认动作
            Menu.SEPARATOR,
            MenuItem('退出', lambda i, item: self.on_quit())
        )
        self.icon = Icon("USB_AutoLocker", self._create_image(self.is_enabled_getter()), "USB 自动锁屏助手", menu)
        return self.icon

    def update_icon(self):
        if self.icon:
            self.icon.icon = self._create_image(self.is_enabled_getter())
            self.icon.update_menu()

    def notify(self, message: str, title: str = "USB AutoLocker"):
        if self.icon:
            self.icon.notify(message, title)

    def stop(self):
        if self.icon:
            self.icon.stop()


# ==================== 设置窗口 ====================

class SettingsWindow(ctk.CTkToplevel):
    """设置窗口"""

    def __init__(self, parent, config_manager: ConfigManager, on_save: Optional[Callable] = None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.on_save_callback = on_save
        self.usb_devices: List[USBDevice] = []
        self._setup_window()
        self._create_widgets()
        self._load_config()
        # 异步加载设备列表，避免阻塞窗口显示
        self.after(100, self._refresh_devices_async)

    def _setup_window(self):
        self.title("USB AutoLocker 设置")
        self.geometry("520x600")
        self.resizable(True, True)
        self.minsize(480, 500)
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - 260
        y = (self.winfo_screenheight() // 2) - 300
        self.geometry(f"+{x}+{y}")
        # 延迟设置置顶，避免干扰控件交互
        self.after(100, lambda: self.attributes("-topmost", True))
        self.after(200, lambda: self.attributes("-topmost", False))
        self.focus_force()

    def _create_widgets(self):
        # 使用可滚动的主容器
        main = ctk.CTkScrollableFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=10, pady=10)

        # USB 设备
        dev_frame = ctk.CTkFrame(main)
        dev_frame.pack(fill="x", pady=(0, 15))
        ctk.CTkLabel(dev_frame, text="🔌 USB 设备", font=("Microsoft YaHei", 14, "bold")).pack(anchor="w", padx=10, pady=(10, 5))
        self.device_listbox = ctk.CTkScrollableFrame(dev_frame, height=100)
        self.device_listbox.pack(fill="x", padx=10, pady=5)
        ctk.CTkButton(dev_frame, text="🔄 刷新", command=self._refresh_devices, width=80).pack(anchor="e", padx=10, pady=5)

        # VID/PID
        vidpid_frame = ctk.CTkFrame(main)
        vidpid_frame.pack(fill="x", pady=(0, 15))
        ctk.CTkLabel(vidpid_frame, text="⚙️ VID/PID", font=("Microsoft YaHei", 14, "bold")).pack(anchor="w", padx=10, pady=(10, 5))
        row = ctk.CTkFrame(vidpid_frame, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(row, text="VID:").pack(side="left", padx=(0, 5))
        self.vid_entry = ctk.CTkEntry(row, width=120, placeholder_text="VID_XXXX")
        self.vid_entry.pack(side="left", padx=(0, 15))
        ctk.CTkLabel(row, text="PID:").pack(side="left", padx=(0, 5))
        self.pid_entry = ctk.CTkEntry(row, width=120, placeholder_text="PID_XXXX")
        self.pid_entry.pack(side="left")

        # 倒计时
        cd_frame = ctk.CTkFrame(main)
        cd_frame.pack(fill="x", pady=(0, 15))
        ctk.CTkLabel(cd_frame, text="⏱️ 倒计时", font=("Microsoft YaHei", 14, "bold")).pack(anchor="w", padx=10, pady=(10, 5))
        cd_row = ctk.CTkFrame(cd_frame, fg_color="transparent")
        cd_row.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(cd_row, text="锁屏倒计时:").pack(side="left", padx=(0, 10))
        self.countdown_var = ctk.StringVar(value="5")
        self.countdown_entry = ctk.CTkEntry(cd_row, width=60, textvariable=self.countdown_var)
        self.countdown_entry.pack(side="left", padx=(0, 5))
        ctk.CTkLabel(cd_row, text="秒 (1-30)").pack(side="left")

        # 其他选项
        opt_frame = ctk.CTkFrame(main)
        opt_frame.pack(fill="x", pady=(0, 15))
        ctk.CTkLabel(opt_frame, text="📋 其他", font=("Microsoft YaHei", 14, "bold")).pack(anchor="w", padx=10, pady=(10, 5))
        self.autostart_var = ctk.BooleanVar()
        ctk.CTkCheckBox(opt_frame, text="开机自动启动", variable=self.autostart_var).pack(anchor="w", padx=10, pady=5)

        # 按钮
        btn_frame = ctk.CTkFrame(main, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(10, 0))
        ctk.CTkButton(btn_frame, text="保存", command=self._save, width=100).pack(side="right", padx=(10, 0))
        ctk.CTkButton(btn_frame, text="取消", command=self.destroy, width=100, fg_color="gray").pack(side="right")

    def _refresh_devices_async(self):
        """异步刷新设备列表"""
        for w in self.device_listbox.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.device_listbox, text="正在扫描设备...", text_color="gray").pack(pady=10)
        threading.Thread(target=self._scan_and_update, daemon=True).start()

    def _scan_and_update(self):
        """在后台线程扫描设备"""
        pythoncom.CoInitialize()
        try:
            devices = USBScanner.scan_devices()
            # 检查窗口是否还存在
            if self.winfo_exists():
                self.after(0, lambda: self._update_device_list(devices))
        finally:
            pythoncom.CoUninitialize()

    def _update_device_list(self, devices: List[USBDevice]):
        """更新设备列表 UI"""
        # 检查窗口和控件是否还存在
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        
        for w in self.device_listbox.winfo_children():
            w.destroy()
        self.usb_devices = devices
        if not self.usb_devices:
            ctk.CTkLabel(self.device_listbox, text="未检测到 USB 设备", text_color="gray").pack(pady=10)
            return
        self.device_var = ctk.StringVar()
        current_vid, current_pid = self.vid_entry.get(), self.pid_entry.get()
        for dev in self.usb_devices:
            rb = ctk.CTkRadioButton(self.device_listbox, text=dev.display_name, variable=self.device_var, value=dev.vid_pid,
                                     command=lambda d=dev: self._select_device(d))
            rb.pack(anchor="w", pady=2)
            if dev.vid == current_vid and dev.pid == current_pid:
                self.device_var.set(dev.vid_pid)

    def _refresh_devices(self):
        """手动刷新按钮调用"""
        self._refresh_devices_async()

    def _select_device(self, dev: USBDevice):
        self.vid_entry.delete(0, "end")
        self.vid_entry.insert(0, dev.vid)
        self.pid_entry.delete(0, "end")
        self.pid_entry.insert(0, dev.pid)

    def _load_config(self):
        cfg = self.config_manager.config
        self.vid_entry.insert(0, cfg.device_vid)
        self.pid_entry.insert(0, cfg.device_pid)
        self.countdown_var.set(str(cfg.countdown_seconds))
        self.autostart_var.set(AutoStartManager.is_enabled())

    def _save(self):
        vid = self.vid_entry.get().strip().upper()
        pid = self.pid_entry.get().strip().upper()
        if not vid.startswith("VID_"):
            vid = f"VID_{vid}"
        if not pid.startswith("PID_"):
            pid = f"PID_{pid}"
        # 验证倒计时秒数
        try:
            countdown = int(self.countdown_var.get())
            countdown = max(1, min(30, countdown))  # 限制在 1-30 之间
        except ValueError:
            countdown = 5
        self.config_manager.update(device_vid=vid, device_pid=pid, countdown_seconds=countdown, auto_start=self.autostart_var.get())
        AutoStartManager.set_enabled(self.autostart_var.get())
        if self.on_save_callback:
            self.on_save_callback()
        self.destroy()


# ==================== 主应用 ====================

class USBAutoLockerApp:
    """主应用程序"""

    def __init__(self):
        self.config_manager = ConfigManager()
        self.usb_monitor = USBMonitor(self.config_manager)
        self.root: Optional[tk.Tk] = None
        self.tray_manager: Optional[TrayIconManager] = None
        self.countdown_popup: Optional[CountdownPopup] = None
        self.settings_window: Optional[SettingsWindow] = None
        self.is_enabled = True
        self.last_shift_time = 0
        self.keyboard_listener = keyboard.Listener(on_release=self._on_key_release)
        self.keyboard_listener.start()

    def _on_key_release(self, key):
        if not self.countdown_popup or not self.countdown_popup.is_showing:
            return
        if key in (keyboard.Key.shift_l, keyboard.Key.shift_r):
            now = time.time()
            if now - self.last_shift_time < 0.5:
                self.countdown_popup.cancel()
            self.last_shift_time = now

    def _execute_lock(self):
        """执行系统锁屏"""
        print("执行锁屏...")
        try:
            # 使用 ctypes 直接调用 Windows API（更可靠）
            ctypes.windll.user32.LockWorkStation()
        except Exception as e:
            print(f"锁屏失败: {e}")
            # 备用方案
            subprocess.run("rundll32.exe user32.dll,LockWorkStation", shell=True)

    def _on_device_removed(self):
        """设备拔出回调"""
        if not self.is_enabled:
            print("自动锁屏已禁用，跳过")
            return
        # 如果已经在倒计时中，不重复触发
        if self.countdown_popup and self.countdown_popup.is_showing:
            print("已在倒计时中，跳过")
            return
        print(f"触发锁屏倒计时 ({self.config_manager.config.countdown_seconds}秒)...")
        self.countdown_popup = CountdownPopup(self.root, self.config_manager.config.countdown_seconds, on_complete=self._execute_lock)
        self.root.after(0, self.countdown_popup.show)

    def _on_device_inserted(self):
        """设备插入回调"""
        # 如果正在倒计时，自动取消
        if self.countdown_popup and self.countdown_popup.is_showing:
            print("设备重新插入，取消锁屏倒计时")
            self.countdown_popup.cancel()
        if self.tray_manager:
            self.tray_manager.notify("USB 密钥已插入", "设备状态")

    def _toggle_enable(self):
        self.is_enabled = not self.is_enabled
        self.config_manager.update(enabled=self.is_enabled)
        if self.tray_manager:
            self.tray_manager.notify(f"自动锁屏{'已启用' if self.is_enabled else '已禁用'}", "状态")

    def _open_settings(self):
        if self.settings_window:
            try:
                if self.settings_window.winfo_exists():
                    # 窗口已存在，激活并置顶
                    self.settings_window.deiconify()  # 如果最小化则恢复
                    self.settings_window.lift()  # 提升到最前
                    self.settings_window.focus_force()  # 强制获取焦点
                    return
            except Exception:
                pass  # 窗口可能已销毁
            self.settings_window = None
        self.root.after(0, self._create_settings)

    def _create_settings(self):
        def on_save():
            self.usb_monitor.restart()
            if self.tray_manager:
                self.tray_manager.notify("配置已保存", "设置")
        self.settings_window = SettingsWindow(self.root, self.config_manager, on_save=on_save)

    def _quit(self):
        self.usb_monitor.stop()
        if self.tray_manager:
            self.tray_manager.stop()
        if self.root:
            self.root.quit()
        os._exit(0)

    def run(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.is_enabled = self.config_manager.config.enabled
        self.usb_monitor.on_device_removed = self._on_device_removed
        self.usb_monitor.on_device_inserted = self._on_device_inserted
        self.usb_monitor.start()
        self.tray_manager = TrayIconManager(on_toggle=self._toggle_enable, on_settings=self._open_settings, on_quit=self._quit, is_enabled_getter=lambda: self.is_enabled)
        threading.Thread(target=self.tray_manager.create().run, daemon=True).start()
        self.root.mainloop()


if __name__ == "__main__":
    mutex = check_single_instance()
    # 如果程序位置变化，自动更新自启动路径
    AutoStartManager.update_path_if_needed()
    USBAutoLockerApp().run()
