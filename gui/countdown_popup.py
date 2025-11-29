"""倒计时弹窗模块"""
import tkinter as tk
from typing import Callable, Optional
import ctypes


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
        """获取 DPI 缩放因子"""
        dpi = window.winfo_fpixels('1i')
        return dpi / 96.0

    def show(self):
        """显示弹窗"""
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

        self.label = tk.Label(
            self.popup,
            text=f"！USB密钥已拔出 ！\n将在 {self.remaining} 秒后锁屏",
            font=("Microsoft YaHei", int(16 * scale), "bold"),
            bg='#ffcccc',
            fg='red'
        )
        self.label.pack(expand=True, pady=20)

        hint = tk.Label(
            self.popup,
            text="连按两次 Shift 键取消",
            font=("Microsoft YaHei", int(10 * scale), "bold"),
            bg='#ffcccc'
        )
        hint.pack(pady=5)

        self._tick()

    def _tick(self):
        """倒计时逻辑"""
        if not self.popup:
            return

        if self.cancelled:
            self._show_cancelled()
            return

        if self.remaining > 0:
            self.label.config(text=f"！USB密钥已拔出 ！\n将在 {self.remaining} 秒后锁屏")
            self.remaining -= 1
            self.root.after(1000, self._tick)
        else:
            self.close()
            self.on_complete()

    def _show_cancelled(self):
        """显示取消状态"""
        if self.label:
            self.label.config(text="！已取消锁屏 ！", fg='green')
        self.root.after(1500, self.close)
        if self.on_cancel:
            self.on_cancel()

    def cancel(self):
        """取消倒计时"""
        self.cancelled = True

    def close(self):
        """关闭弹窗"""
        if self.popup:
            self.popup.destroy()
            self.popup = None
            self.label = None

    @property
    def is_showing(self) -> bool:
        """是否正在显示"""
        return self.popup is not None
