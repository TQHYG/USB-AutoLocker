import time
import threading
import subprocess
import wmi
import ctypes
import tkinter as tk
from tkinter import messagebox
from pystray import Icon, Menu, MenuItem
from PIL import Image, ImageDraw
from pynput import keyboard
import pythoncom
import win32com.client as com_client

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)  # 1=System DPI, 2=Per-Monitor DPI
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

# ================= 配置区域 =================
YOUR_DEVICE_VID = "VID_1050"  # 请替换为你的设备VID
YOUR_DEVICE_PID = "PID_0407"  # 请替换为你的设备PID
# ===========================================

TARGET_DEVICE_ID = f"%{YOUR_DEVICE_VID}&{YOUR_DEVICE_PID}%"
DEVICE_PNP_ID = f"USB\\{YOUR_DEVICE_VID}&{YOUR_DEVICE_PID}" 

class USBAutoLocker:
    def __init__(self):
        self.is_enabled = True
        self.is_counting_down = False
        self.cancel_lock = False
        self.last_ctrl_time = 0
        self.icon = None
        self.root = None # Tkinter 主窗口
        self.wmi_thread = None
        self.monitor_lock = threading.Lock() # 用于防止 WMI 多次触发
        self.device_present = False # 初始状态标记

        # 启动键盘监听
        self.listener = keyboard.Listener(on_release=self.on_key_release)
        self.listener.start()

    # --- 锁屏与UI操作 ---
    
    def get_scale_factor(self, window):
        """获取当前窗口所在显示器的缩放因子"""
        dpi = window.winfo_fpixels('1i')   # 当前显示器 DPI
        return dpi / 96.0                  # Windows 默认 96 DPI


    def execute_lock(self):
        """执行系统锁屏"""
        if self.is_enabled and not self.cancel_lock:
            print("执行锁屏...")
            subprocess.run("rundll32.exe user32.dll,LockWorkStation", shell=True)

    def show_warning_popup(self):
        """在主线程中显示倒计时弹窗"""
        if self.monitor_lock.locked():
            return # 避免重复弹窗
        self.monitor_lock.acquire()

        self.is_counting_down = True
        self.cancel_lock = False
            
        # --- Tkinter 窗口创建 ---
        popup = tk.Toplevel(self.root)
        popup.attributes("-topmost", True)
        popup.overrideredirect(True)

        scale_factor = self.get_scale_factor(popup)
        w, h = int(500 * scale_factor), int(160 * scale_factor)
        x = (popup.winfo_screenwidth()//2) - (w//2)
        y = (popup.winfo_screenheight()//2) - (h//2)
        popup.geometry(f"{w}x{h}+{x}+{y}")
        popup.configure(bg='#ffcccc')

        self.label = tk.Label(popup, text="！USB密钥已拔出 ！\n将在 5 秒后锁屏", font=("Microsoft YaHei", int(16 * scale_factor), "bold"), bg='#ffcccc', fg='red')
        self.label.pack(expand=True, pady=20)
            
        hint = tk.Label(popup, text="连按两次 Shift 键取消", font=("Microsoft YaHei", int(10 * scale_factor), "bold"), bg='#ffcccc')
        hint.pack(pady=5)
        
        self.popup = popup

        # 调度倒计时
        self.countdown_logic(5)


    def countdown_logic(self, count):
        """倒计时逻辑"""
        if not self.root: return

        if self.cancel_lock:
            self.update_popup_label("！已取消锁屏 ！")
            self.root.after(1000, self.close_popup) # 1秒后关闭
            return

        if count > 0:
            self.update_popup_label(f"！USB密钥已拔出 ！\n将在 {count} 秒后锁屏")
            self.root.after(1000, lambda: self.countdown_logic(count - 1))
        else:
            self.close_popup()
            self.execute_lock()

    def update_popup_label(self, text):
        """更新弹窗文字"""
        if self.root:
            self.label.config(text=text)

    def close_popup(self):
        """关闭弹窗并释放锁"""
        self.is_counting_down = False
        if hasattr(self, "popup") and self.popup:
            self.popup.destroy()
            self.popup = None
        if self.monitor_lock.locked():
            self.monitor_lock.release() 

    # --- 托盘与键盘监听 ---
    
    def create_tray_icon(self):
        width = 64
        height = 64
        image = Image.new('RGB', (width, height), color=(255, 255, 255))
        dc = ImageDraw.Draw(image)
        dc.rectangle((20, 28, 44, 52), outline="black", fill="black")

        dc.arc((20, 8, 44, 36), start=0, end=180, fill="black")
        dc.line((20, 22, 20, 28), fill="black", width=4)
        dc.line((44, 22, 44, 28), fill="black", width=4)

        menu = Menu(
            MenuItem('启用自动锁屏', self.toggle_enable, checked=lambda item: self.is_enabled),
            MenuItem('退出', self.quit_app)
        )
        self.icon = Icon("USB_Locker", image, "USB 自动锁屏助手", menu)
        

        
    def toggle_enable(self, icon, item):
        self.is_enabled = not self.is_enabled
        state = "已启用" if self.is_enabled else "已禁用"
        self.icon.notify(f"自动锁屏功能{state}", "状态更新")

    def quit_app(self, icon, item):
        # 释放所有资源并强制退出
        self.icon.stop()
        if self.root:
            self.root.quit()
        # 强制结束进程
        import os
        os._exit(0)

    def on_key_release(self, key):
        """监听键盘释放事件，检测双击shift"""
        if not self.is_counting_down:
            return

        if key == keyboard.Key.shift_l or key == keyboard.Key.shift_r:
            current_time = time.time()
            if current_time - self.last_ctrl_time < 0.5:
                self.cancel_lock = True
                if self.root:
                    self.root.after(0, self.update_popup_label, "！已取消锁屏 ！")
                    self.root.after(2000, self.close_popup) # 1秒后关闭
            self.last_ctrl_time = current_time

    # --- WMI 监听 ---

    def check_initial_device_presence(self):
        """检查设备初始状态，解决启动时不存在的问题"""
        try:
            c = wmi.WMI()
            # 搜索 Win32_PnPEntity 中 DeviceID 包含目标 ID 的设备
            results = c.query(f"SELECT DeviceID FROM Win32_PnPEntity WHERE DeviceID LIKE '{DEVICE_PNP_ID}%'")
            self.device_present = bool(results)
            print(f"初始设备存在状态: {self.device_present}")
        except Exception as e:
            print(f"初始设备检测失败: {e}")
            self.device_present = False


    def device_monitor_loop(self):
        """WMI 监听线程，同时监听插入和拔出事件"""
        # 线程初始化 COM 库
        pythoncom.CoInitialize()

        try:
            c = wmi.WMI()
            print(f"开始监听设备 {TARGET_DEVICE_ID}...")
            
            # --- 1. 监听删除事件 (Deletion) ---
            device_disconnect_query = f"SELECT * FROM __InstanceDeletionEvent WITHIN 1 WHERE TargetInstance ISA 'Win32_PnPEntity' AND TargetInstance.DeviceID LIKE '{TARGET_DEVICE_ID}'"
            watcher_deletion = c.watch_for(raw_wql=device_disconnect_query)
            
            # --- 2. 监听创建事件 (Insertion/Creation) ---
            device_connect_query = f"SELECT * FROM __InstanceCreationEvent WITHIN 1 WHERE TargetInstance ISA 'Win32_PnPEntity' AND TargetInstance.DeviceID LIKE '{TARGET_DEVICE_ID}'"
            watcher_creation = c.watch_for(raw_wql=device_connect_query)

            while True:
                # --- 检查拔出事件 ---
                try:
                    # 使用 100ms 超时，允许检查第二个 watcher
                    event_deletion = watcher_deletion(timeout_ms=100) 
                    
                    if event_deletion and not self.monitor_lock.locked():
                        
                        if self.is_enabled and self.device_present:
                            print("WMI 检测到设备拔出！触发锁屏流程。")
                            self.root.after(0, self.show_warning_popup)
                            self.device_present = False # 标记为已拔出
                        
                        elif self.device_present:
                            # 设备存在，但锁屏功能被用户禁用，只更新状态
                            print("WMI 检测到设备拔出，但功能已禁用。")
                            self.device_present = False 
                            
                except wmi.x_wmi_timed_out:
                    pass # 正常超时，继续循环
                
                # --- 检查插入事件 ---
                try:
                    # 使用 100ms 超时
                    event_creation = watcher_creation(timeout_ms=100)
                    
                    if event_creation:
                        if not self.device_present:
                            print("WMI 检测到设备重新插入！已激活自动锁屏。")
                            self.device_present = True # 标记为已插入
                        
                except wmi.x_wmi_timed_out:
                    pass # 正常超时，继续循环
                
                except Exception as e:
                    print(f"监听循环发生错误: {e}")
                    time.sleep(2)

        finally:
            pythoncom.CoUninitialize()

    def start(self):
        # 主线程先创建 Tk 根窗口
        self.root = tk.Tk()
        self.root.withdraw()
        """启动程序"""
        # 1. 检查初始状态
        self.check_initial_device_presence()
        
        # 2. 启动 WMI 监听线程
        self.wmi_thread = threading.Thread(target=self.device_monitor_loop, daemon=True)
        self.wmi_thread.start()
        
        # 3. 设置 Tray Icon 对象
        self.create_tray_icon()
        threading.Thread(target=self.icon.run, daemon=True).start()
        self.root.mainloop()

if __name__ == "__main__":
    app = USBAutoLocker()
    app.start()
    
    try:
        app.icon.run()
    except KeyboardInterrupt:
        print("主程序被终止。")