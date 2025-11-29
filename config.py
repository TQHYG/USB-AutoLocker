"""配置管理模块"""
import json
import os
from dataclasses import dataclass, asdict
from typing import Optional

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")

@dataclass
class AppConfig:
    """应用配置数据类"""
    device_vid: str = "VID_1050"
    device_pid: str = "PID_0407"
    device_name: str = ""  # 设备友好名称（可选）
    countdown_seconds: int = 5
    auto_start: bool = False
    enabled: bool = True

    def get_device_id_pattern(self) -> str:
        """获取 WMI 查询用的设备 ID 模式"""
        return f"%{self.device_vid}&{self.device_pid}%"

    def get_pnp_id(self) -> str:
        """获取 PnP 设备 ID 前缀"""
        return f"USB\\{self.device_vid}&{self.device_pid}"


class ConfigManager:
    """配置文件管理器"""
    
    def __init__(self, config_path: str = CONFIG_FILE):
        self.config_path = config_path
        self.config = self.load()

    def load(self) -> AppConfig:
        """加载配置文件"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return AppConfig(**data)
            except (json.JSONDecodeError, TypeError) as e:
                print(f"配置文件读取失败，使用默认配置: {e}")
        return AppConfig()

    def save(self, config: Optional[AppConfig] = None) -> bool:
        """保存配置到文件"""
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
        """更新配置项"""
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
        self.save()
