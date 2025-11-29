"""USB 监控模块"""
import threading
import time
import wmi
import pythoncom
from typing import Callable, Optional
from config import ConfigManager


class USBMonitor:
    """USB 设备监控器"""

    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.device_present = False
        self.running = False
        self.thread: Optional[threading.Thread] = None
        
        # 回调函数
        self.on_device_removed: Optional[Callable] = None
        self.on_device_inserted: Optional[Callable] = None

    def _get_device_pattern(self) -> str:
        """获取当前配置的设备 ID 模式"""
        return self.config_manager.config.get_device_id_pattern()

    def _get_pnp_id(self) -> str:
        """获取当前配置的 PnP ID"""
        return self.config_manager.config.get_pnp_id()

    def check_device_presence(self) -> bool:
        """检查设备是否存在"""
        try:
            c = wmi.WMI()
            pnp_id = self._get_pnp_id()
            results = c.query(f"SELECT DeviceID FROM Win32_PnPEntity WHERE DeviceID LIKE '{pnp_id}%'")
            return bool(results)
        except Exception as e:
            print(f"设备检测失败: {e}")
            return False

    def _monitor_loop(self):
        """监控循环（在独立线程中运行）"""
        pythoncom.CoInitialize()

        try:
            c = wmi.WMI()
            device_pattern = self._get_device_pattern()
            print(f"开始监听设备 {device_pattern}...")

            # 监听删除事件
            deletion_query = f"SELECT * FROM __InstanceDeletionEvent WITHIN 1 WHERE TargetInstance ISA 'Win32_PnPEntity' AND TargetInstance.DeviceID LIKE '{device_pattern}'"
            watcher_deletion = c.watch_for(raw_wql=deletion_query)

            # 监听创建事件
            creation_query = f"SELECT * FROM __InstanceCreationEvent WITHIN 1 WHERE TargetInstance ISA 'Win32_PnPEntity' AND TargetInstance.DeviceID LIKE '{device_pattern}'"
            watcher_creation = c.watch_for(raw_wql=creation_query)

            while self.running:
                # 检查拔出事件
                try:
                    event = watcher_deletion(timeout_ms=100)
                    if event and self.device_present:
                        print("检测到设备拔出！")
                        self.device_present = False
                        if self.on_device_removed:
                            self.on_device_removed()
                except wmi.x_wmi_timed_out:
                    pass

                # 检查插入事件
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
        """启动监控"""
        if self.running:
            return

        # 检查初始状态
        self.device_present = self.check_device_presence()
        print(f"初始设备状态: {'已连接' if self.device_present else '未连接'}")

        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()

    def stop(self):
        """停止监控"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
            self.thread = None

    def restart(self):
        """重启监控（配置更改后调用）"""
        self.stop()
        time.sleep(0.5)
        self.start()
