---
name: microsoft-workiq
description: Search and interact with Microsoft 365 content (emails, files, Teams chats, calendar events, people, external connectors) via WorkIQ MCP server. Use when the user asks to search M365/Outlook/Teams/OneDrive/SharePoint content, find emails, look up people, check calendar events, open M365 items, find colleagues, check org structure, or query external connectors. Triggers on phrases like "search email", "find in Teams", "look up files", "who is", "whoami", "find people", "open this", "search calendar", "find in SharePoint", "who reports to", "how many people in".
---

# Microsoft WorkIQ

Interact with Microsoft 365 via the local WorkIQ MCP server at `http://127.0.0.1:52366/mcp`.

All tool names are **lowercase**. Every call requires a `conversation_id` string parameter — use a stable id per conversation (e.g. `"session-001"`).

## ⚠️ Prerequisites

This skill requires the **WorkIQ MCP server** to be running locally. It does NOT ship with MicroClaw and must be set up separately.

### Setup Steps

1. **Install WorkIQ**
   WorkIQ is an internal Microsoft tool. Install it via the internal package manager or follow your team's setup guide.

2. **Start the MCP server**
   Ensure WorkIQ's MCP endpoint is running on `http://127.0.0.1:52366/mcp`.
   - On Windows, WorkIQ typically runs as a background service or tray app.
   - Verify it's running: `curl http://127.0.0.1:52366/mcp` should return a response (or connection accepted).

3. **Authenticate**
   WorkIQ uses your Microsoft Entra ID (AAD) credentials. Make sure you are signed in to your Microsoft account.
   - If the MCP server returns authentication errors, re-authenticate via the WorkIQ app.

4. **Firewall / Proxy**
   - The MCP server binds to `127.0.0.1` (localhost only) — no firewall rule needed.
   - If you're behind a corporate proxy, WorkIQ handles Graph API calls directly; no proxy config needed for this skill.

### Troubleshooting

| Symptom | Fix |
|---------|-----|
| `Connection refused` on port 52366 | WorkIQ MCP server is not running. Start it. |
| `405 Method Not Allowed` | Server is running but needs MCP protocol init. The script handles this automatically. |
| Auth errors / 401 | Re-sign-in to WorkIQ or refresh your AAD token. |
| Empty search results | Check that your M365 tenant has the content indexed. Try searching in Outlook/Teams directly first. |

## Tools

### whoami

Get the signed-in user's profile from Microsoft Graph.

```bash
pwsh "<skill_dir>/scripts/mcp-call.ps1" whoami '{"conversation_id":"<cid>"}'
```

Optional: `direct_reports_size` (int, 1–100, default 30)

### search

Search across M365 data.

```bash
pwsh "<skill_dir>/scripts/mcp-call.ps1" search '{"conversation_id":"<cid>","query":"<q>"}'
```

Parameters:
- `query` (string, required) — search query
- `source` (string, optional, default `"all"`) — `all`, `email`, `files`, `chat`, `events`, `external`
- `connector` (string, optional) — external connector name (when source=external)
- `size` (int, optional, 1–25, default 10) — results per page
- `from` (int, optional, default 0) — pagination offset

### open

Open/read a search result by its read handle. Returns full, partial, or snippet content.

```bash
pwsh "<skill_dir>/scripts/mcp-call.ps1" open '{"conversation_id":"<cid>","read_handle":"<handle>"}'
```

- `read_handle` (string, required) — opaque handle from a search result

### find_people

Find people in the Microsoft Graph directory.

```bash
pwsh "<skill_dir>/scripts/mcp-call.ps1" find_people '{"conversation_id":"<cid>","query":"<q>"}'
```

Optional filters: `alias`, `principalName`, `displayName`, `department`, `office`, `title`, `size` (1–50), `include_direct_reports` (bool), `direct_reports_size` (1–100)

### count_people

Count people matching filters (returns count only).

```bash
pwsh "<skill_dir>/scripts/mcp-call.ps1" count_people '{"conversation_id":"<cid>","department":"<dept>"}'
```

Same filter params as find_people (except size/include_direct_reports).

## Notes

- MCP server must be running on port 52366.
- The script handles the full MCP lifecycle (initialize → initialized → tools/call) per invocation.
- Search results include `read_handle` fields — use these with the `open` tool to read full content.
- Present results concisely: subject, sender, date, snippet. Offer to open items for details.
