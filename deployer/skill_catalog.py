"""Bundled skill catalog for the OpenClaw deployer.

Each entry maps a skill directory name → metadata dict.
The ``certified`` flag marks skills pre-approved for the default allowlist.

Certification rule
------------------
certified=True when the skill:
  • runs locally with no external API key, OR
  • is an OpenAI skill (MS collaboration partner), OR
  • talks only to the OpenClaw ecosystem (clawhub).
"""

from __future__ import annotations
from typing import TypedDict


class SkillInfo(TypedDict):
    description: str
    certified: bool


# Complete catalog of the 52 bundled skills shipped with OpenClaw.
# Keep alphabetically sorted by key.
SKILL_CATALOG: dict[str, SkillInfo] = {
    "1password":          {"description": "1Password 密码管理集成",               "certified": False},
    "apple-notes":        {"description": "Apple 备忘录管理",                     "certified": True},
    "apple-reminders":    {"description": "Apple 提醒事项管理",                   "certified": True},
    "bear-notes":         {"description": "Bear 笔记管理（需 API 密钥）",         "certified": False},
    "blogwatcher":        {"description": "博客和 RSS 订阅监控",                  "certified": True},
    "blucli":             {"description": "BluOS 音响控制",                       "certified": True},
    "bluebubbles":        {"description": "iMessage 集成（需 API 密钥）",         "certified": False},
    "camsnap":            {"description": "RTSP/ONVIF 摄像头抓帧",               "certified": True},
    "canvas":             {"description": "HTML 内容展示到 OpenClaw 节点",        "certified": True},
    "clawhub":            {"description": "搜索安装 AgentSkill 市场技能",         "certified": True},
    "coding-agent":       {"description": "委派编码任务给子代理",                 "certified": True},
    "discord":            {"description": "Discord 消息操作（需 API 密钥）",      "certified": False},
    "eightctl":           {"description": "Eight Sleep 床垫控制（需 API 密钥）",  "certified": False},
    "gemini":             {"description": "Google Gemini AI（需 API 密钥）",      "certified": False},
    "gh-issues":          {"description": "GitHub Issue 修复代理（需 Token）",    "certified": False},
    "gifgrep":            {"description": "GIF 搜索工具（需 API 密钥）",          "certified": False},
    "github":             {"description": "GitHub CLI 操作（需 Token）",          "certified": False},
    "gog":                {"description": "Google Workspace 集成（需 API 密钥）", "certified": False},
    "goplaces":           {"description": "Google Places API（需 API 密钥）",     "certified": False},
    "healthcheck":        {"description": "主机安全加固与风险配置",               "certified": True},
    "himalaya":           {"description": "CLI 邮件客户端（需 IMAP 配置）",       "certified": False},
    "imsg":               {"description": "iMessage/SMS 收发",                    "certified": True},
    "mcporter":           {"description": "MCP 服务器管理",                       "certified": True},
    "model-usage":        {"description": "模型用量与成本统计",                   "certified": True},
    "nano-banana-pro":    {"description": "Gemini 图像生成（需 API 密钥）",       "certified": False},
    "nano-pdf":           {"description": "自然语言编辑 PDF",                     "certified": True},
    "notion":             {"description": "Notion 页面与数据库（需 API 密钥）",   "certified": False},
    "obsidian":           {"description": "Obsidian 笔记库管理",                  "certified": True},
    "openai-image-gen":   {"description": "OpenAI 图像生成（需 API 密钥）",       "certified": True},
    "openai-whisper":     {"description": "本地语音转文字（离线）",               "certified": True},
    "openai-whisper-api": {"description": "OpenAI 语音转文字 API",               "certified": True},
    "openhue":            {"description": "Philips Hue 灯光控制",                "certified": True},
    "oracle":             {"description": "AI 代码分析最佳实践",                  "certified": True},
    "ordercli":           {"description": "Foodora 订单查询（需 API 密钥）",      "certified": False},
    "peekaboo":           {"description": "macOS UI 自动化与截图",               "certified": True},
    "sag":                {"description": "ElevenLabs TTS（需 API 密钥）",       "certified": False},
    "session-logs":       {"description": "搜索分析会话日志",                     "certified": True},
    "sherpa-onnx-tts":    {"description": "本地文本转语音（离线）",               "certified": True},
    "skill-creator":      {"description": "创建和编辑 AgentSkill",               "certified": True},
    "slack":              {"description": "Slack 消息管理（需 API 密钥）",        "certified": False},
    "songsee":            {"description": "音频频谱可视化",                       "certified": True},
    "sonoscli":           {"description": "Sonos 音响控制",                       "certified": True},
    "spotify-player":     {"description": "Spotify 播放控制（需 API 密钥）",      "certified": False},
    "summarize":          {"description": "URL/播客/文件摘要（需 API 密钥）",     "certified": False},
    "things-mac":         {"description": "Things 3 任务管理（需 API 密钥）",     "certified": False},
    "tmux":               {"description": "tmux 会话远程控制",                    "certified": True},
    "trello":             {"description": "Trello 看板管理（需 API 密钥）",       "certified": False},
    "video-frames":       {"description": "视频帧提取（ffmpeg）",                 "certified": True},
    "voice-call":         {"description": "语音通话（需 API 密钥）",              "certified": False},
    "wacli":              {"description": "WhatsApp 消息收发",                    "certified": True},
    "weather":            {"description": "天气查询（wttr.in/Open-Meteo）",       "certified": True},
    "xurl":               {"description": "X (Twitter) API 客户端（需 API 密钥）","certified": False},
}


def get_certified_skills() -> list[str]:
    """Return sorted list of skill names where certified=True."""
    return sorted(k for k, v in SKILL_CATALOG.items() if v["certified"])


def get_all_skill_names() -> list[str]:
    """Return all skill names sorted alphabetically."""
    return sorted(SKILL_CATALOG.keys())


def export_catalog_json() -> dict[str, dict]:
    """Return the full catalog as a JSON-serializable dict."""
    return {k: dict(v) for k, v in SKILL_CATALOG.items()}
