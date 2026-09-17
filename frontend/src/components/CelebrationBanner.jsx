import { useEffect, useState } from "react";
import { api } from "../api.js";

export default function CelebrationBanner({ items = [] }) {
  const [visible, setVisible] = useState(items || []);

  useEffect(() => {
    setVisible(items || []);
  }, [items]);

  if (!visible.length) return null;
  const note = visible[0];

  async function dismiss() {
    try {
      await api.celebrationSeen(note.key);
    } catch {
      /* still hide locally */
    }
    setVisible((prev) => prev.filter((row) => row.key !== note.key));
  }

  return (
    <aside className="celebration-banner" data-testid="celebration-banner" role="status">
      <p className="celebration-copy">{note.message}</p>
      <button type="button" className="cta ghost compact" onClick={dismiss}>
        Quiet
      </button>
    </aside>
  );
}
