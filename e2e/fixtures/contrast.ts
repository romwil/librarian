import { expect, type Locator, type Page } from "@playwright/test";

/** 1×1 PNG so peek `has-wash` is true without a real jacket. */
export const TINY_COVER_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
);

export async function contrastRatio(locator: Locator): Promise<number> {
  return locator.evaluate((el) => {
    const parse = (c: string) => {
      if (!c || c === "transparent") return null;
      const srgb = String(c).match(/color\(srgb ([\d.]+) ([\d.]+) ([\d.]+)(?: \/ ([\d.]+))?/);
      if (srgb) {
        return {
          r: Math.round(+srgb[1] * 255),
          g: Math.round(+srgb[2] * 255),
          b: Math.round(+srgb[3] * 255),
          a: srgb[4] === undefined ? 1 : +srgb[4],
        };
      }
      const m = String(c).match(/rgba?\((\d+)[, ]+(\d+)[, ]+(\d+)(?:[, /]+([\d.]+))?/);
      if (!m) return null;
      return { r: +m[1], g: +m[2], b: +m[3], a: m[4] === undefined ? 1 : +m[4] };
    };
    const lin = (c: number) => {
      const v = c / 255;
      return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
    };
    const lum = ({ r, g, b }: { r: number; g: number; b: number }) => 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
    const blend = (fg: { r: number; g: number; b: number; a: number }, bg: { r: number; g: number; b: number }) => ({
      r: fg.r * fg.a + bg.r * (1 - fg.a),
      g: fg.g * fg.a + bg.g * (1 - fg.a),
      b: fg.b * fg.a + bg.b * (1 - fg.a),
      a: 1,
    });
    const htmlBg = parse(getComputedStyle(document.documentElement).backgroundColor) || {
      r: 243,
      g: 236,
      b: 223,
      a: 1,
    };
    const stack: { r: number; g: number; b: number; a: number }[] = [];
    let n: HTMLElement | null = el as HTMLElement;
    while (n && n !== document.documentElement) {
      const c = parse(getComputedStyle(n).backgroundColor);
      if (c && c.a > 0) stack.push(c);
      n = n.parentElement;
    }
    let acc = htmlBg;
    for (let i = stack.length - 1; i >= 0; i--) acc = blend(stack[i], acc);
    const color = parse(getComputedStyle(el as HTMLElement).color);
    if (!color) return 0;
    const fg = color.a < 1 ? blend(color, acc) : color;
    const L1 = lum(fg);
    const L2 = lum(acc);
    const hi = Math.max(L1, L2);
    const lo = Math.min(L1, L2);
    return (hi + 0.05) / (lo + 0.05);
  });
}

export async function backgroundAlpha(locator: Locator): Promise<number> {
  return locator.evaluate((el) => {
    const c = getComputedStyle(el).backgroundColor;
    const srgb = String(c).match(/color\(srgb [\d.]+ [\d.]+ [\d.]+(?: \/ ([\d.]+))?/);
    if (srgb) return srgb[1] === undefined ? 1 : +srgb[1];
    const m = String(c).match(/rgba?\((\d+)[, ]+(\d+)[, ]+(\d+)(?:[, /]+([\d.]+))?/);
    if (!m) return 0;
    return m[4] === undefined ? 1 : +m[4];
  });
}

export async function expectReadable(locator: Locator, min = 4.5) {
  await expect(locator).toBeVisible();
  const ratio = await contrastRatio(locator);
  const sample = await locator.evaluate((el) => ({
    text: (el.textContent || "").slice(0, 80),
    color: getComputedStyle(el).color,
    bg: getComputedStyle(el).backgroundColor,
  }));
  expect(ratio, `${sample.text} ${sample.color} on ${sample.bg}`).toBeGreaterThanOrEqual(min);
}

export const PEEK_WORK = {
  id: "peek-gladwell",
  title: "Revenge of the Tipping Point",
  author: "Malcolm Gladwell",
  kind: "book",
  year: 2024,
  description:
    "Twenty-five years after The Tipping Point, Malcolm Gladwell returns to the subject of social epidemics.",
  has_cover: true,
  review_state: "",
};

export const PEEK_DETAIL = {
  work: PEEK_WORK,
  files: [{ id: "f1", filename: "revenge.epub", kind: "book", size: 1200, on_disk: true }],
  file_count: 1,
  can_open: true,
  can_download: true,
  can_read: true,
  listen: { can_listen: false },
  favorite: false,
  related: [],
  progress: { fraction: 0.2, position: "" },
};

export async function mockPeekHall(page: Page) {
  await page.route("**/api/hall**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        continue: [PEEK_WORK],
        listening: [],
        whats_new: [],
        favorites: [],
        books: [],
        magazines: [],
        comics: [],
        audiobooks: [],
        music: [],
      }),
    });
  });
  await page.route("**/api/works/peek-gladwell/cover", async (route) => {
    await route.fulfill({ status: 200, contentType: "image/png", body: TINY_COVER_PNG });
  });
  await page.route("**/api/works/peek-gladwell", async (route) => {
    if (route.request().method() !== "GET") {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(PEEK_DETAIL),
    });
  });
}
