/** Gaps as gifts — invitation copy for Hall rails. */

export function gapsGiftPresence(hall) {
  const fromServer = String(hall?.gaps_presence || "").trim();
  if (fromServer) return fromServer;
  const count = Array.isArray(hall?.gaps) ? hall.gaps.length : 0;
  if (count < 1) return "The runs on these shelves feel whole tonight.";
  if (count === 1) return "One gentle hole invites the next chapter.";
  return `${count} gentle holes invite the next chapters of a run.`;
}

export function gapsGiftTitle() {
  return "Gaps as gifts";
}

export function gapsGiftKicker(hall) {
  return gapsGiftPresence(hall);
}
