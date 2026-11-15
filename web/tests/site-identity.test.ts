import assert from "node:assert/strict";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import test from "node:test";

const url = (path: string) => new URL(path, import.meta.url);
const read = (path: string) => readFileSync(url(path), "utf8");

test("every page's tab title is Cues, set once in the root layout", () => {
  assert.match(read("../app/layout.tsx"), /title: "Cues",/);
  const pages = readdirSync(url("../app/"), { recursive: true })
    .map(String)
    .filter((name) => /page\.tsx$/.test(name));
  assert.ok(pages.length > 5, "found the pages");
  for (const page of pages) {
    const source = read(`../app/${page}`);
    // No page overrides the title (no "Cues · …" suffixes).
    assert.doesNotMatch(source, /export const metadata|generateMetadata|title:/, page);
  }
});

test("the tab icon is the Cues mark, not the Next.js template favicon", () => {
  assert.equal(existsSync(url("../app/favicon.ico")), false);
  assert.ok(existsSync(url("../app/icon.svg")));
  assert.ok(existsSync(url("../app/apple-icon.png")));
  assert.match(read("../app/icon.svg"), /M30\.92 55\.98/); // the Cues mark's arm
});

test("the website offers only the built-in tasks, never custom gestures", () => {
  const files = readdirSync(url("../components/"))
    .filter((name) => /^landing.*\.tsx$/.test(name))
    .map((name) => `../components/${name}`);
  assert.ok(files.length > 5, "found the landing components");
  for (const file of files)
    assert.doesNotMatch(
      read(file),
      /own gesture|record(ed)? (a |your )?gesture|gesture you record|teacher-recorded|custom gesture|recorded by you|wave hello|touch your nose/i,
      file,
    );
});
