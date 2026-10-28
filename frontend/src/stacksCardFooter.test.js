import assert from "node:assert/strict";
import { describe, it } from "vitest";
import { stacksCardIdentity, stacksCardLine } from "./components/StacksCardFooter.jsx";

describe("stacks card identity", () => {
  it("names the title and the author", () => {
    assert.deepEqual(stacksCardIdentity({ title: "The 1619 Project", author: "Nikole Hannah-Jones" }), {
      title: "The 1619 Project",
      author: "Nikole Hannah-Jones",
    });
  });

  it("falls back to the book title and drops a blank author", () => {
    assert.deepEqual(stacksCardIdentity({ book_title: "Circe", author: "   " }), {
      title: "Circe",
      author: "",
    });
    assert.deepEqual(stacksCardIdentity({}), { title: "Untitled", author: "" });
  });

  it("keeps a hostile title as one plain line", () => {
    const hostile = "<script>alert(1)</script>\n<img src=x onerror=alert(1)>";
    assert.equal(stacksCardLine(hostile), "<script>alert(1)</script> <img src=x onerror=alert(1)>");
    assert.equal(stacksCardIdentity(null).title, "Untitled");
    assert.equal(stacksCardIdentity(undefined).author, "");
    assert.equal(stacksCardLine({ bad: true }), "");
    assert.equal(stacksCardLine(["Nikole"]), "");
    assert.equal(stacksCardLine(Number.NaN), "");
    const huge = "A".repeat(5000);
    assert.equal(stacksCardIdentity({ title: huge, author: huge }).title, huge);
  });
});
