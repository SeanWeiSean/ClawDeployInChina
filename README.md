# 🦞 OpenClaw Deployer — 中国网络环境部署工具

一键在 **中国大陆网络环境** 下完成 [OpenClaw](https://github.com/openclaw) 的部署。

工具自动处理国内网络访问不畅的问题（Node.js 使用 npmmirror 镜像源，npm registry 切换至淘宝源），并提供图形化界面，无需手动操作命令行。

## 功能

- **WSL2 模式**：自动安装 Ubuntu 24.04 → Node.js → pnpm → OpenClaw，配置 systemd
- **Windows 原生模式**：从 npmmirror 下载 Node.js，直接在 Windows 上安装 OpenClaw
- 自动写入 LiteLLM 模型配置并启动 Gateway 服务
- 图形化部署界面，适合非技术人员使用

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/SeanWeiSean/ClawDeployInChina.git
cd ClawDeployInChina
```

### 2. 创建虚拟环境并安装依赖

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

# 安装可选依赖（推荐）
pip install -r requirements.txt
```

> 项目核心功能无需额外依赖（tkinter 随 Python 自带，YAML 有内置 fallback），但建议安装 `pyyaml` 以获得完整的 YAML 支持。

### 3. 配置模型 API Key

复制 `.env.example` 为 `.env`，填入你自己的模型端点和密钥：

```bash
cp .env.example .env
```

编辑 `.env`：

```ini
MODEL_BASE_URL=https://your-litellm-proxy-url.example.com
MODEL_API_KEY=sk-your-api-key-here
```

> **⚠️ `.env` 文件包含敏感信息，已被 `.gitignore` 排除，不会被提交到仓库。**

### 4. 启动部署器

双击 `launch.bat`，或手动运行：

```bash
python deploy.py
```

程序会请求管理员权限（WSL 安装需要），确认 UAC 弹窗后即可看到部署界面。

## 项目结构

```
├── deploy.py              # 主程序 & GUI 入口
├── deployer/
│   ├── config.py          # 配置管理（从 .env 读取密钥）
│   ├── logger.py          # 日志模块
│   ├── openclaw_setup.py  # WSL 内 OpenClaw 安装逻辑
│   ├── windows_setup.py   # Windows 原生安装逻辑
│   └── wsl_manager.py     # WSL2 管理
├── scripts/
│   ├── setup-wsl.sh       # WSL 初始化脚本
│   └── configure-openclaw.sh
├── .env.example           # 环境变量模板（安全提交）
├── config.yaml            # 部署配置（非敏感部分）
├── launch.bat             # Windows 快捷启动
└── requirements.txt
```

## 配置说明

| 配置项 | 位置 | 说明 |
|---|---|---|
| `MODEL_API_KEY` | `.env` | **必填** — 你的 LLM API 密钥 |
| `MODEL_BASE_URL` | `.env` | **必填** — LiteLLM 代理端点 |
| WSL 发行版、Node 版本等 | `config.yaml` | 可选，默认值已可直接使用 |

## 要求

- Windows 10/11（需开启 WSL2 功能，或使用 Windows 原生模式）
- Python 3.10+（运行部署器本身）
- 网络连接（npmmirror 镜像可在国内访问）

## License

MIT
