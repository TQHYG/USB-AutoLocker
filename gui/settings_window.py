"""设置窗口模块"""
import customtkinter as ctk
from typing import Callable, Optional
from config import AppConfig, ConfigManager
from utils.usb_scanner import USBScanner, USBDevice
from utils.autostart import AutoStartManager


class SettingsWindow(ctk.CTkToplevel):
    """设置窗口"""

    def __init__(self, parent, config_manager: ConfigManager, on_save: Optional[Callable] = None):
        super().__init__(parent)
        
        self.config_manager = config_manager
        self.on_save_callback = on_save
        self.usb_devices: list[USBDevice] = []
        
        self._setup_window()
        self._create_widgets()
        self._load_current_config()
        self._refresh_devices()

    def _setup_window(self):
        """设置窗口属性"""
        self.title("USB AutoLocker 设置")
        self.geometry("500x480")
        self.resizable(False, False)
        
        # 居中显示
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (500 // 2)
        y = (self.winfo_screenheight() // 2) - (480 // 2)
        self.geometry(f"+{x}+{y}")
        
        # 置顶
        self.attributes("-topmost", True)
        self.grab_set()

    def _create_widgets(self):
        """创建界面组件"""
        # 主容器
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # === USB 设备选择区域 ===
        device_frame = ctk.CTkFrame(main_frame)
        device_frame.pack(fill="x", pady=(0, 15))
        
        ctk.CTkLabel(device_frame, text="🔌 USB 设备", font=("Microsoft YaHei", 14, "bold")).pack(anchor="w", padx=10, pady=(10, 5))
        
        # 设备列表
        self.device_listbox = ctk.CTkScrollableFrame(device_frame, height=120)
        self.device_listbox.pack(fill="x", padx=10, pady=5)
        
        # 刷新按钮
        ctk.CTkButton(device_frame, text="🔄 刷新设备列表", command=self._refresh_devices, width=120).pack(anchor="e", padx=10, pady=5)

        # === VID/PID 手动输入区域 ===
        vidpid_frame = ctk.CTkFrame(main_frame)
        vidpid_frame.pack(fill="x", pady=(0, 15))
        
        ctk.CTkLabel(vidpid_frame, text="⚙️ 手动配置 VID/PID", font=("Microsoft YaHei", 14, "bold")).pack(anchor="w", padx=10, pady=(10, 5))
        
        input_row = ctk.CTkFrame(vidpid_frame, fg_color="transparent")
        input_row.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(input_row, text="VID:").pack(side="left", padx=(0, 5))
        self.vid_entry = ctk.CTkEntry(input_row, width=120, placeholder_text="VID_XXXX")
        self.vid_entry.pack(side="left", padx=(0, 15))
        
        ctk.CTkLabel(input_row, text="PID:").pack(side="left", padx=(0, 5))
        self.pid_entry = ctk.CTkEntry(input_row, width=120, placeholder_text="PID_XXXX")
        self.pid_entry.pack(side="left")

        # === 倒计时设置 ===
        countdown_frame = ctk.CTkFrame(main_frame)
        countdown_frame.pack(fill="x", pady=(0, 15))
        
        ctk.CTkLabel(countdown_frame, text="⏱️ 倒计时设置", font=("Microsoft YaHei", 14, "bold")).pack(anchor="w", padx=10, pady=(10, 5))
        
        countdown_row = ctk.CTkFrame(countdown_frame, fg_color="transparent")
        countdown_row.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(countdown_row, text="锁屏倒计时:").pack(side="left", padx=(0, 10))
        self.countdown_slider = ctk.CTkSlider(countdown_row, from_=1, to=30, number_of_steps=29, width=200)
        self.countdown_slider.pack(side="left", padx=(0, 10))
        self.countdown_label = ctk.CTkLabel(countdown_row, text="5 秒")
        self.countdown_label.pack(side="left")
        self.countdown_slider.configure(command=self._on_countdown_change)

        # === 其他选项 ===
        options_frame = ctk.CTkFrame(main_frame)
        options_frame.pack(fill="x", pady=(0, 15))
        
        ctk.CTkLabel(options_frame, text="📋 其他选项", font=("Microsoft YaHei", 14, "bold")).pack(anchor="w", padx=10, pady=(10, 5))
        
        self.autostart_var = ctk.BooleanVar()
        self.autostart_check = ctk.CTkCheckBox(options_frame, text="开机自动启动", variable=self.autostart_var)
        self.autostart_check.pack(anchor="w", padx=10, pady=5)

        # === 按钮区域 ===
        btn_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(10, 0))
        
        ctk.CTkButton(btn_frame, text="保存", command=self._save_config, width=100).pack(side="right", padx=(10, 0))
        ctk.CTkButton(btn_frame, text="取消", command=self.destroy, width=100, fg_color="gray").pack(side="right")

    def _refresh_devices(self):
        """刷新 USB 设备列表"""
        # 清空现有列表
        for widget in self.device_listbox.winfo_children():
            widget.destroy()
        
        self.usb_devices = USBScanner.scan_devices()
        
        if not self.usb_devices:
            ctk.CTkLabel(self.device_listbox, text="未检测到 USB 设备", text_color="gray").pack(pady=10)
            return
        
        self.device_var = ctk.StringVar()
        current_vid = self.vid_entry.get()
        current_pid = self.pid_entry.get()
        
        for device in self.usb_devices:
            rb = ctk.CTkRadioButton(
                self.device_listbox,
                text=device.display_name,
                variable=self.device_var,
                value=device.vid_pid,
                command=lambda d=device: self._on_device_select(d)
            )
            rb.pack(anchor="w", pady=2)
            
            # 如果匹配当前配置，选中它
            if device.vid == current_vid and device.pid == current_pid:
                self.device_var.set(device.vid_pid)

    def _on_device_select(self, device: USBDevice):
        """设备选择回调"""
        self.vid_entry.delete(0, "end")
        self.vid_entry.insert(0, device.vid)
        self.pid_entry.delete(0, "end")
        self.pid_entry.insert(0, device.pid)

    def _on_countdown_change(self, value):
        """倒计时滑块变化回调"""
        seconds = int(value)
        self.countdown_label.configure(text=f"{seconds} 秒")

    def _load_current_config(self):
        """加载当前配置到界面"""
        config = self.config_manager.config
        
        self.vid_entry.insert(0, config.device_vid)
        self.pid_entry.insert(0, config.device_pid)
        self.countdown_slider.set(config.countdown_seconds)
        self.countdown_label.configure(text=f"{config.countdown_seconds} 秒")
        self.autostart_var.set(AutoStartManager.is_enabled())

    def _save_config(self):
        """保存配置"""
        vid = self.vid_entry.get().strip().upper()
        pid = self.pid_entry.get().strip().upper()
        
        # 格式校验
        if not vid.startswith("VID_"):
            vid = f"VID_{vid}"
        if not pid.startswith("PID_"):
            pid = f"PID_{pid}"
        
        countdown = int(self.countdown_slider.get())
        autostart = self.autostart_var.get()
        
        # 更新配置
        self.config_manager.update(
            device_vid=vid,
            device_pid=pid,
            countdown_seconds=countdown,
            auto_start=autostart
        )
        
        # 设置开机自启
        AutoStartManager.set_enabled(autostart)
        
        # 回调通知
        if self.on_save_callback:
            self.on_save_callback()
        
        self.destroy()
