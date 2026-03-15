---
name: microsoft-browser-control
description: Control a local browser via Playwright for web automation, testing, scraping, and interaction. Use when the user asks to open a webpage, fill a form, click buttons, take screenshots, extract page content, run UI tests, or automate browser workflows. Triggers on phrases like "open this URL", "take a screenshot", "fill in the form", "click the button", "scrape the page", "check this website", "navigate to", "browser automation".
---

# Microsoft Browser Control

Automate and interact with local browser instances via Playwright.

Supports headed (visible) and headless modes for web automation, UI testing, content extraction, form filling, and screenshot capture.

## ⚠️ Prerequisites

This skill requires **Playwright** to be installed locally. It does NOT ship with MicroClaw and must be set up separately.

### Setup Steps

1. **Install Playwright**
   ```bash
   npm install -g playwright
   npx playwright install chromium
   ```

2. **Verify installation**
   ```bash
   npx playwright --version
   ```

### Troubleshooting

| Symptom | Fix |
|---------|-----|
| `playwright: command not found` | Run `npm install -g playwright` |
| Browser binaries not found | Run `npx playwright install chromium` |
| Timeout on page load | Check network connectivity or increase timeout |
| Page blocked by CORS/CSP | Use headed mode for sites requiring interaction |

## Tools

### navigate

Open a URL in the browser and return the page title and status.

```bash
pwsh "<skill_dir>/scripts/browser-control.ps1" navigate '{"url":"https://example.com"}'
```

Parameters:
- `url` (string, required) — URL to navigate to
- `headless` (bool, optional, default `true`) — run in headless mode
- `timeout` (int, optional, default 30000) — navigation timeout in ms

### screenshot

Take a screenshot of the current page or a specific element.

```bash
pwsh "<skill_dir>/scripts/browser-control.ps1" screenshot '{"url":"https://example.com","output":"screenshot.png"}'
```

Parameters:
- `url` (string, required) — URL to screenshot
- `output` (string, optional, default `"screenshot.png"`) — output file path
- `selector` (string, optional) — CSS selector to screenshot a specific element
- `full_page` (bool, optional, default `false`) — capture full scrollable page

### extract

Extract text content, HTML, or structured data from a page.

```bash
pwsh "<skill_dir>/scripts/browser-control.ps1" extract '{"url":"https://example.com","selector":"h1"}'
```

Parameters:
- `url` (string, required) — URL to extract from
- `selector` (string, optional) — CSS selector to extract specific elements
- `format` (string, optional, default `"text"`) — `text`, `html`, or `json`

### click

Click an element on the page.

```bash
pwsh "<skill_dir>/scripts/browser-control.ps1" click '{"url":"https://example.com","selector":"button.submit"}'
```

Parameters:
- `url` (string, required) — URL to navigate to
- `selector` (string, required) — CSS selector of element to click
- `wait_after` (int, optional, default 1000) — ms to wait after click

### fill

Fill in form fields on a page.

```bash
pwsh "<skill_dir>/scripts/browser-control.ps1" fill '{"url":"https://example.com","fields":[{"selector":"#email","value":"user@example.com"}]}'
```

Parameters:
- `url` (string, required) — URL to navigate to
- `fields` (array, required) — list of `{"selector": "...", "value": "..."}` objects
- `submit_selector` (string, optional) — CSS selector of submit button to click after filling

### evaluate

Run arbitrary JavaScript on a page and return the result.

```bash
pwsh "<skill_dir>/scripts/browser-control.ps1" evaluate '{"url":"https://example.com","script":"document.title"}'
```

Parameters:
- `url` (string, required) — URL to navigate to
- `script` (string, required) — JavaScript expression to evaluate

## Notes

- Each tool invocation launches a fresh browser context (no shared state between calls).
- For multi-step workflows (navigate → fill → click → screenshot), chain tool calls sequentially.
- Headless mode is the default. Use `headless: false` for debugging or sites that detect headless browsers.
- Screenshots are saved relative to the current working directory unless an absolute path is given.
- The skill respects `robots.txt` — do not use it to scrape sites that disallow automation.
