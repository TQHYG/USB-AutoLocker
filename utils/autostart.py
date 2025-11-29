"""开机自启管理模块"""
import os
import sys
import winreg

APP_NAME = "USB-AutoLocker"


class AutoStartManager:
    """Windows 开机自启管理器"""

    REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"

    @classmethod
    def get_exe_path(cls) -> str:
        """获取当前程序路径"""
        if getattr(sys, 'frozen', False):
            # PyInstaller 打包后
            return sys.executable
        else:
            # 开发环境
            main_script = os.path.join(os.path.dirname(__file__), '..', 'main.py')
            return f'pythonw "{os.path.abspath(main_script)}"'

    @classmethod
    def is_enabled(cls) -> bool:
        """检查是否已启用开机自启"""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                cls.REG_PATH,
                0,
                winreg.KEY_READ
            )
            try:
                winreg.QueryValueEx(key, APP_NAME)
                return True
            except FileNotFoundError:
                return False
            finally:
                winreg.CloseKey(key)
        except Exception:
            return False

    @classmethod
    def enable(cls) -> bool:
        """启用开机自启"""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                cls.REG_PATH,
                0,
                winreg.KEY_SET_VALUE
            )
            exe_path = cls.get_exe_path()
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, exe_path)
            winreg.CloseKey(key)
            return True
        except Exception as e:
            print(f"启用开机自启失败: {e}")
            return False

    @classmethod
    def disable(cls) -> bool:
        """禁用开机自启"""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                cls.REG_PATH,
                0,
                winreg.KEY_SET_VALUE
            )
            try:
                winreg.DeleteValue(key, APP_NAME)
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
        if enabled:
            return cls.enable()
        else:
            return cls.disable()
