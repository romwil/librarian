/** Safe undo for grooming — confidence without fear. */

export function undoIsAvailable(undo) {
  return Boolean(undo?.available);
}

export function undoPresence(undo) {
  const fromServer = String(undo?.presence || "").trim();
  if (fromServer) return fromServer;
  if (undoIsAvailable(undo)) {
    return "The last tend can still be undone.";
  }
  return "No recent tend to undo — the lamp keeps calm.";
}

export function undoLabel(undo) {
  return String(undo?.label || "").trim() || "Last tend";
}
