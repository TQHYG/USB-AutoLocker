"""USB 设备扫描模块"""
import re
from dataclasses import dataclass
from typing import List, Optional
import wmi


@dataclass
class USBDevice:
    """USB 设备信息"""
    vid: str  # 如 "VID_1050"
    pid: str  # 如 "PID_0407"
    name: str  # 设备名称
    device_id: str  # 完整设备 ID

    @property
    def display_name(self) -> str:
        """显示名称"""
        return f"{self.name} ({self.vid}&{self.pid})"

    @property
    def vid_pid(self) -> str:
        """VID&PID 组合"""
        return f"{self.vid}&{self.pid}"


class USBScanner:
    """USB 设备扫描器"""

    # 匹配 VID 和 PID 的正则
    VID_PID_PATTERN = re.compile(r'VID_([0-9A-Fa-f]{4})&PID_([0-9A-Fa-f]{4})', re.IGNORECASE)

    @classmethod
    def scan_devices(cls) -> List[USBDevice]:
        """扫描当前连接的所有 USB 设备"""
        devices = []
        seen = set()  # 用于去重

        try:
            c = wmi.WMI()
            # 查询所有 USB 设备
            for device in c.Win32_PnPEntity():
                device_id = device.DeviceID or ""
                
                # 只处理 USB 设备
                if not device_id.startswith("USB\\"):
                    continue

                match = cls.VID_PID_PATTERN.search(device_id)
                if match:
                    vid = f"VID_{match.group(1).upper()}"
                    pid = f"PID_{match.group(2).upper()}"
                    vid_pid = f"{vid}&{pid}"

                    # 去重
                    if vid_pid in seen:
                        continue
                    seen.add(vid_pid)

                    name = device.Name or device.Description or "未知设备"
                    devices.append(USBDevice(
                        vid=vid,
                        pid=pid,
                        name=name,
                        device_id=device_id
                    ))

        except Exception as e:
            print(f"USB 扫描失败: {e}")

        return devices

    @classmethod
    def find_device(cls, vid: str, pid: str) -> Optional[USBDevice]:
        """查找指定 VID/PID 的设备"""
        devices = cls.scan_devices()
        for device in devices:
            if device.vid.upper() == vid.upper() and device.pid.upper() == pid.upper():
                return device
        return None

    @classmethod
    def is_device_connected(cls, vid: str, pid: str) -> bool:
        """检查指定设备是否已连接"""
        return cls.find_device(vid, pid) is not None
