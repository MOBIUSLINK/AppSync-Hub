# 🚀 AppSync Hub - 智能软件资源镜像与分发中心

> 一个基于 Python 的自动化软件资源同步、缓存与极速分发系统，为团队或个人提供企业级的软件镜像库。

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.8%2B-brightgreen)
![Flask](https://img.shields.io/badge/framework-Flask-lightgrey)

## ✨ 核心特性

- **🤖 智能链接嗅探 (Playwright 驱动)**：无视反爬与动态加载！内置无头浏览器引擎，不仅支持正则表达式提取，还能穿透 Vue/React 等单页应用，甚至自动执行 JS 点击并拦截真实下载流。
- **⚡ 极速缓存与流式分发**：一旦发现新版本，后台将自动下载缓存。当用户请求下载时，如果本地有缓存则直接触发极速下发（支持断点续传）；如果没有缓存，则开启透明流代理（透传源站下载进度与文件体积）。
- **🕒 全局定时同步 (APScheduler)**：告别手动维护！系统会在凌晨空闲时段自动巡检所有配置的软件，发现更新则立刻静默拉取。
- **📊 现代化管理面板**：提供可视化软件配置、抓取规则正则沙盒测试、运行日志实时推送（基于 SSE 协议），以及 Live Console 终端监听。
- **📦 轻量级免部署架构**：采用 TinyDB 基于单 JSON 文件的本地数据库，摆脱 MySQL/Redis 的繁重依赖。内置 Waitress 生产级多线程服务器，即插即用。

## 🛠️ 技术栈

- **后端**: Python 3, Flask, Waitress
- **调度引擎**: APScheduler
- **抓取与防盗链穿透**: Playwright, Requests, BeautifulSoup4
- **数据存储**: TinyDB
- **前端**: HTML5, Bootstrap 5, Jinja2, SSE (Server-Sent Events)

## 📦 快速开始

### 1. 克隆项目与环境准备
```bash
git clone https://github.com/your-username/appsync-hub.git
cd appsync-hub
```

### 2. 安装核心依赖
建议在 Python 3.8 或以上环境中运行：
```bash
pip install -r requirements.txt
```

### 3. 安装无头浏览器驱动
因为项目使用了 Playwright 进行动态网页的提取与渲染，需安装对应的 Chromium 引擎：
```bash
playwright install chromium
```

### 4. 基础配置
在运行之前，请打开 `config.py`，将默认的管理员密码修改为您自己的密码：
```python
ADMIN_PASSWORD = "your_admin_password"  # 👈 建议修改为您自己的专属密码
```

### 5. 启动服务
```bash
python app.py
```
> 服务默认在 `0.0.0.0:5000` 端口启动，支持多线程并发。
> 请在浏览器中访问管理后台：[http://localhost:5000](http://localhost:5000)

## ⚙️ 核心抓取规则解析

在管理面板中添加/编辑软件时，您可以使用多重策略链来嗅探下载链接：

1. **硬编码直链**：最高优先级，若厂商提供了固定不变的最新版直链，可直接使用。
2. **正则表达式提取**：在网页源码中通过正则精确捕获下载链接。
3. **CSS / DOM 节点匹配**：通过网页节点的 `class`、`id` 或 `href` 属性智能抓取。
4. **模糊后缀捕获**：作为兜底方案，全页面检索包含 `.exe`、`.dmg`、`.apk` 等后缀的 A 标签。

> **💡 小贴士**：面板内置了 **“智能正则生成与测试沙盒”** 工具，您可以直接粘贴大厂官网的源码，在沙盒中一键验证规则，告别盲目测试。

## 📄 许可证

本项目采用 [MIT License](LICENSE) 开源许可证。
