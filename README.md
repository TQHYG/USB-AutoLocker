# AutoLocker

一个基于 USB 设备的自动锁屏工具。  
当指定的 USB 设备（例如安全 U 盘）拔出时，程序会在倒计时后自动锁定 Windows 系统。  
支持托盘图标控制、设置窗口配置 VID/PID、DPI 适配和美化弹窗。

## ✨ 功能特性
- 🔒 USB 拔出后自动锁屏
- 🖼️ 托盘图标显示锁状态（闭合=启用，打开=禁用）
- ⚙️ 设置窗口可配置目标 USB 设备 VID/PID
- 📂 配置文件自动保存和加载（`config.json`）
- 🖥️ 高 DPI 适配，字体和窗口在高分屏下清晰显示
- ⏱️ 倒计时弹窗，支持取消锁屏操作

## 📦 安装依赖
```bash
pip install -r requirements.txt
