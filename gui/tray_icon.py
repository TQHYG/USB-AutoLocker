"""托盘图标模块"""
from pystray import Icon, Menu, MenuItem
from PIL import Image, ImageDraw
from typing import Callable, Optional


class TrayIconManager:
    """托盘图标管理器"""

    def __init__(
        self,
        on_toggle_enable: Callable,
        on_open_settings: Callable,
        on_quit: Callable,
        is_enabled_getter: Callable[[], bool]
    ):
        self.on_toggle_enable = on_toggle_enable
        self.on_open_settings = on_open_settings
        self.on_quit = on_quit
        self.is_enabled_getter = is_enabled_getter
        self.icon: Optional[Icon] = None

    def _create_icon_image(self, is_enabled: bool) -> Image.Image:
        """创建托盘图标图像"""
        width, height = 64, 64
        image = Image.new('RGB', (width, height), color=(255, 255, 255))
        dc = ImageDraw.Draw(image)
        
        # 锁体
        dc.rectangle((15, 28, 50, 51), outline="black", fill="black")
        dc.line((23, 22, 23, 28), fill="black", width=4)

        if is_enabled:
            # 闭合锁环
            dc.arc((22, 12, 42, 36), start=180, end=0, fill="black", width=4)
            dc.line((40, 22, 40, 28), fill="black", width=4)
        else:
            # 打开锁环
            dc.arc((22, 12, 42, 36), start=180, end=300, fill="black", width=4)

        return image

    def _create_menu(self) -> Menu:
        """创建托盘菜单"""
        return Menu(
            MenuItem(
                '启用自动锁屏',
                self._on_toggle,
                checked=lambda item: self.is_enabled_getter()
            ),
            MenuItem('设置', self._on_settings),
            Menu.SEPARATOR,
            MenuItem('退出', self._on_quit)
        )

    def _on_toggle(self, icon, item):
        """切换启用状态"""
        self.on_toggle_enable()
        self.update_icon()

    def _on_settings(self, icon, item):
        """打开设置"""
        self.on_open_settings()

    def _on_quit(self, icon, item):
        """退出程序"""
        self.on_quit()

    def create(self) -> Icon:
        """创建托盘图标"""
        is_enabled = self.is_enabled_getter()
        image = self._create_icon_image(is_enabled)
        menu = self._create_menu()
        
        self.icon = Icon(
            "USB_AutoLocker",
            image,
            "USB 自动锁屏助手",
            menu
        )
        return self.icon

    def update_icon(self):
        """更新图标状态"""
        if self.icon:
            is_enabled = self.is_enabled_getter()
            self.icon.icon = self._create_icon_image(is_enabled)
            self.icon.update_menu()

    def notify(self, message: str, title: str = "USB AutoLocker"):
        """显示通知"""
        if self.icon:
            self.icon.notify(message, title)

    def stop(self):
        """停止托盘图标"""
        if self.icon:
            self.icon.stop()
