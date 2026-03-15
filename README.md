# 🦞 OpenClaw Deployer — 中国网络环境部署工具

一键在 **中国大陆网络环境** 下完成 [OpenClaw](https://github.com/openclaw) 的部署。

工具自动处理国内网络访问不畅的问题（Node.js 使用 npmmirror 镜像源，npm registry 切换至淘宝源），并提供图形化界面，无需手动操作命令行。

## 功能

- **自动安装 Git**：从 npmmirror 镜像下载 PortableGit，无需手动安装
- **WSL2 模式**：自动安装 Ubuntu 24.04 → Node.js → pnpm → OpenClaw，配置 systemd
- **Windows 原生模式**：从 npmmirror 下载 Node.js，直接在 Windows 上安装 OpenClaw
- 自动写入 LiteLLM 模型配置并启动 Gateway 服务
- npm registry 自动切换淘宝源，国内下载不卡
- 图形化部署界面，适合非技术人员使用
- 可打包为单文件 exe，双击即用

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

### 使用 exe（无需 Python 环境）

也可直接使用打包好的 `OpenClawDeployer.exe`，双击运行即可，无需安装 Python。

> 注意：exe 旁边需要有 `.env` 文件，填入你的 API Key。

## 部署器自动安装的依赖

部署器会自动在目标机器上安装以下软件，无需用户手动操作：

| 软件 | 来源 | 安装位置 |
|---|---|---|
| Git | npmmirror 镜像（PortableGit） | `~/.openclaw-git/` |
| Node.js 22 | npmmirror 镜像 | `~/.openclaw-node/` |
| OpenClaw | npm（淘宝源） | npm global |

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

---

## WorkIQ — M365 Connector（MCP 插件）

通过 WorkIQ M365 Connector，可以让任何 OpenClaw agent 访问 Microsoft 365 数据（邮件、日历、文件等）。

### 使用步骤

#### 1. 启动 M365 Connector 服务

在工作电脑上运行：

```bash
npx m365connector
```

> 如果没有 npx，可以让 Claude Code 帮你安装（`npm install -g npx`），或直接安装 Node.js。

#### 2. 安装浏览器插件

浏览器插件已放在仓库的 `WorkIQ/` 目录下（`m365-connector-v1.2.4 2.zip`）。

1. 解压 zip 文件
2. 在 Chrome/Edge 中打开 `chrome://extensions/`，开启「开发者模式」
3. 点击「加载已解压的扩展程序」，选择解压后的文件夹
4. 插件安装后会弹出登录页面，完成登录即可

#### 3. 在 Agent 中配置 MCP

在任意 agent 的配置中添加以下 MCP 服务：

```json
"M365Connector": {
  "type": "http",
  "url": "http://127.0.0.1:52366/mcp"
}
```

配置完成后，agent 即可通过 MCP 协议访问你的 M365 数据。
