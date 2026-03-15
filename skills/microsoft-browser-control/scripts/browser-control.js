#!/usr/bin/env node
/**
 * Browser control via Playwright.
 *
 * Usage: node browser-control.js <action> <json-params>
 *
 * Actions: navigate, screenshot, extract, click, fill, evaluate
 *
 * Playwright must be installed globally or in the managed node_modules:
 *   npm install -g playwright && npx playwright install chromium
 */
"use strict";

const [,, action, paramsJson] = process.argv;

if (!action || !paramsJson) {
  console.error("Usage: node browser-control.js <action> <json-params>");
  process.exit(1);
}

let playwright;
try {
  playwright = require("playwright");
} catch {
  console.error("Playwright not found. Install it: npm install -g playwright && npx playwright install chromium");
  process.exit(1);
}

const p = JSON.parse(paramsJson);

(async () => {
  const browser = await playwright.chromium.launch({
    headless: p.headless !== false,
  });
  const page = await browser.newPage();

  try {
    await page.goto(p.url, {
      timeout: p.timeout || 30000,
      waitUntil: "domcontentloaded",
    });

    switch (action) {
      case "navigate": {
        const title = await page.title();
        console.log(JSON.stringify({ title, url: page.url() }));
        break;
      }

      case "screenshot": {
        const output = p.output || "screenshot.png";
        if (p.selector) {
          await page.locator(p.selector).screenshot({ path: output });
          console.log(JSON.stringify({ saved: output, selector: p.selector }));
        } else {
          await page.screenshot({ path: output, fullPage: !!p.full_page });
          console.log(JSON.stringify({ saved: output, fullPage: !!p.full_page }));
        }
        break;
      }

      case "extract": {
        const sel = p.selector || "body";
        const format = p.format || "text";
        if (format === "html") {
          console.log(await page.locator(sel).innerHTML());
        } else {
          console.log(await page.locator(sel).innerText());
        }
        break;
      }

      case "click": {
        await page.locator(p.selector).click();
        await page.waitForTimeout(p.wait_after || 1000);
        console.log(JSON.stringify({ clicked: p.selector, title: await page.title() }));
        break;
      }

      case "fill": {
        for (const f of p.fields) {
          await page.locator(f.selector).fill(f.value);
        }
        if (p.submit_selector) {
          await page.locator(p.submit_selector).click();
          await page.waitForTimeout(1000);
        }
        console.log(JSON.stringify({ filled: p.fields.length, title: await page.title() }));
        break;
      }

      case "evaluate": {
        const result = await page.evaluate(p.script);
        console.log(JSON.stringify({ result }));
        break;
      }

      default:
        console.error("Unknown action: " + action);
        process.exit(1);
    }
  } finally {
    await browser.close();
  }
})();
