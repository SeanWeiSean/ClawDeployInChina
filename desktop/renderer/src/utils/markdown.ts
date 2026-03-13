import DOMPurify from "dompurify";
import MarkdownIt from "markdown-it";
import hljs from "highlight.js";
import "highlight.js/styles/github.css";

const md = new MarkdownIt({
  html: false,
  linkify: true,
  typographer: true,
  highlight(str: string, lang: string): string {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return `<pre class="hljs"><code>${hljs.highlight(str, { language: lang }).value}</code></pre>`;
      } catch {
        // Fall through
      }
    }
    return `<pre class="hljs"><code>${md.utils.escapeHtml(str)}</code></pre>`;
  },
});

const ALLOWED_TAGS = [
  "a", "b", "blockquote", "br", "code", "del", "em",
  "h1", "h2", "h3", "h4", "hr", "i", "li", "ol",
  "p", "pre", "strong", "table", "tbody", "td", "th",
  "thead", "tr", "ul", "img",
];
const ALLOWED_ATTR = ["class", "href", "rel", "target", "title", "start", "src", "alt"];

export function renderMarkdown(text: string): string {
  if (!text.trim()) return "";
  const raw = md.render(text);
  return DOMPurify.sanitize(raw, {
    ALLOWED_TAGS,
    ALLOWED_ATTR,
  });
}
