import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8");

test("the theme icon animates only after a switch, never on first paint", () => {
  const toggle = read("../components/theme-toggle.tsx");
  assert.match(toggle, /useState\(false\)/);
  assert.match(toggle, /switched \? "theme-icon-in" : undefined/);
  assert.match(toggle, /onClick=\{\(\) => \{\s*setSwitched\(true\);/);
  const css = read("../app/globals.css");
  assert.match(css, /\.theme-icon-in \{\s*animation: theme-icon-in 300ms cubic-bezier\(0\.2, 0, 0, 1\) both;/);
  assert.match(css, /prefers-reduced-motion: reduce\) \{\s*\.theme-icon-in \{\s*animation: theme-icon-fade/);
});

test("in the hero, every chip keeps its comma", () => {
  const hero = read("../components/landing-hero.tsx");
  // No comma is left outside a chip group (the old ",{" "}" after a chip).
  assert.ok(!hero.includes(',{" "}'));
  const groups = hero.match(/<span className="ln-chip-group">[\s\S]*?<\/span>\s*,\s*<\/span>/g) ?? [];
  assert.equal(groups.length, 2);
  assert.match(read("../components/landing.css"), /\.ln-chip-group \{\s*white-space: nowrap;/);
});

test("landing copy is Title Case with small words in lower case", () => {
  const small = /\b[A-Z][a-z]+ (A|An|The|Or|For|To|By|Of|And|In|Into|On|At|With|Nor|But|As)\b(?= [A-Z(])/;
  for (const file of [
    "landing.tsx",
    "landing-faq.tsx",
    "landing-needs.tsx",
    "landing-steps.tsx",
    "landing-footer.tsx",
  ]) {
    const source = read(`../components/${file}`);
    const hit = source.match(small);
    assert.equal(hit, null, `${file}: "${hit?.[0]}" should keep the small word in lower case`);
  }
});

test("the sign-in pages: a readable hint and the same header controls as the landing page", () => {
  const css = read("../components/auth.css");
  const hint = css.match(/\.auth-hint \{[^}]*\}/)?.[0] ?? "";
  assert.match(hint, /color: var\(--auth-ink-soft\)/);
  const toggle = css.match(/\.auth-theme-toggle \{[^}]*\}/)?.[0] ?? "";
  assert.match(toggle, /border-radius: 50%/);
  const sw = css.match(/\.auth-switch \{[^}]*\}/)?.[0] ?? "";
  assert.match(sw, /border-radius: 999px/);
});
