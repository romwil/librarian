const ALLOWED_TAGS = new Set(["p", "br", "em", "strong", "i", "b", "ul", "ol", "li", "h3", "h4"]);
const VOID_TAGS = new Set(["br"]);

export function looksLikeHtml(text) {
  return /<[a-z][\s\S]*>/i.test(String(text || ""));
}

/** Strict allowlist sanitizer for catalog blurbs (no attributes, no scripts). */
export function sanitizeDescriptionHtml(html) {
  let text = String(html || "");
  if (!text) return "";
  text = text.replace(/<(script|style|iframe|object|embed)[\s\S]*?<\/\1>/gi, "");
  text = text.replace(/<\/?(script|style|iframe|object|embed)[^>]*>/gi, "");
  text = text.replace(/<\/?([a-z0-9]+)(\s[^>]*)?>/gi, (match, tag) => {
    const name = String(tag || "").toLowerCase();
    if (!ALLOWED_TAGS.has(name)) return "";
    if (VOID_TAGS.has(name)) return "<br>";
    if (match.startsWith("</")) return `</${name}>`;
    return `<${name}>`;
  });
  return text.trim();
}
