// @vitest-environment jsdom
import assert from "node:assert/strict";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, it } from "vitest";
import ProfileMenu from "./components/ProfileMenu.jsx";

const realFetch = globalThis.fetch;
const user = { display_name: "Ada", role: "owner" };

function renderMenu(props = {}) {
  return render(
    <MemoryRouter>
      <p>Outside the menu</p>
      <ProfileMenu user={user} owner {...props} />
    </MemoryRouter>,
  );
}

describe("ProfileMenu on the shared popover", () => {
  beforeEach(() => {
    globalThis.fetch = async () => new Response("{}", { status: 200, headers: { "content-type": "application/json" } });
  });
  afterEach(() => {
    globalThis.fetch = realFetch;
  });

  it("opens from the Library card and closes on Escape", async () => {
    renderMenu();
    const trigger = screen.getByRole("button", { name: "Library card Ada OWNER" });
    assert.equal(trigger.getAttribute("aria-expanded"), "false");
    await userEvent.click(trigger);
    assert.equal(trigger.getAttribute("aria-expanded"), "true");
    assert.ok(screen.getByRole("dialog", { name: "Library card" }));
    await userEvent.keyboard("{Escape}");
    assert.equal(screen.queryByRole("dialog", { name: "Library card" }), null);
  });

  it("closes on a pointer outside but stays open for the text-size slider", async () => {
    renderMenu();
    await userEvent.click(screen.getByRole("button", { name: /^Library card/ }));
    const slider = screen.getByRole("slider", { name: /Text size/ });
    fireEvent.pointerDown(slider);
    assert.ok(screen.getByRole("dialog", { name: "Library card" }));
    fireEvent.pointerDown(screen.getByText("Outside the menu"));
    assert.equal(screen.queryByRole("dialog", { name: "Library card" }), null);
  });

  it("keeps in-menu pointer gestures away from other document dismiss listeners", async () => {
    renderMenu();
    await userEvent.click(screen.getByRole("button", { name: /^Library card/ }));
    let leaked = 0;
    const listener = () => {
      leaked += 1;
    };
    document.addEventListener("pointerdown", listener);
    try {
      fireEvent.pointerDown(screen.getByRole("radio", { name: "Lights Down" }));
    } finally {
      document.removeEventListener("pointerdown", listener);
    }
    assert.equal(leaked, 0);
    assert.ok(screen.getByRole("dialog", { name: "Library card" }));
  });

  it("picks a theme and follows a link, closing the menu", async () => {
    const themes = [];
    renderMenu({ onThemeChange: (value) => themes.push(value) });
    await userEvent.click(screen.getByRole("button", { name: /^Library card/ }));
    await userEvent.click(screen.getByRole("radio", { name: "Lights Down" }));
    assert.deepEqual(themes, ["lights_down"]);
    assert.ok(screen.getByRole("dialog", { name: "Library card" }));
    await userEvent.click(screen.getByRole("link", { name: "Settings" }));
    assert.equal(screen.queryByRole("dialog", { name: "Library card" }), null);
  });

  it("hides owner links from a reader", async () => {
    renderMenu({ owner: false, user: { display_name: "Kid", role: "reader" } });
    await userEvent.click(screen.getByRole("button", { name: /^Library card/ }));
    assert.equal(screen.queryByRole("link", { name: "Settings" }), null);
    assert.ok(screen.getByRole("link", { name: "Your library" }));
  });
});
