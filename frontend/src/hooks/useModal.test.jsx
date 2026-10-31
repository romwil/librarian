// @vitest-environment jsdom
import assert from "node:assert/strict";
import { useRef, useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it } from "vitest";
import useModal, { getFocusable } from "./useModal.js";

function Trap({ open, onEscape }) {
  const panelRef = useRef(null);
  const cancelRef = useRef(null);
  useModal({ open, onEscape, panelRef, initialFocusRef: cancelRef });
  if (!open) return null;
  return (
    <div ref={panelRef} role="dialog" aria-modal="true" aria-label="Trap">
      <input aria-label="Count" />
      <button ref={cancelRef} type="button" onClick={onEscape}>
        Cancel
      </button>
      <button type="button">Confirm</button>
    </div>
  );
}

function Shell() {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button type="button" onClick={() => setOpen(true)}>
        Open
      </button>
      <Trap open={open} onEscape={() => setOpen(false)} />
    </div>
  );
}

describe("useModal", () => {
  it("lists inputs and buttons as focusable", () => {
    const root = document.createElement("div");
    root.innerHTML = `<input><button>Go</button><button disabled>Nope</button>`;
    const nodes = getFocusable(root);
    assert.equal(nodes.length, 2);
    assert.equal(nodes[0].tagName, "INPUT");
  });

  it("traps Tab, Escape dismisses, and focus returns to the opener", async () => {
    const user = userEvent.setup();
    render(<Shell />);
    await user.click(screen.getByRole("button", { name: "Open" }));
    const cancel = await screen.findByRole("button", { name: "Cancel" });
    assert.equal(document.activeElement, cancel);

    await user.tab();
    assert.equal(document.activeElement, screen.getByRole("button", { name: "Confirm" }));
    await user.tab();
    assert.equal(document.activeElement, screen.getByLabelText("Count"));
    await user.tab({ shift: true });
    assert.equal(document.activeElement, screen.getByRole("button", { name: "Confirm" }));

    await user.keyboard("{Escape}");
    assert.equal(screen.queryByRole("dialog"), null);
    assert.equal(document.activeElement, screen.getByRole("button", { name: "Open" }));
  });
});
