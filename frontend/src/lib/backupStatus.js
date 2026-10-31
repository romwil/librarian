/**
 * Maintain "Last backup" line. Reads the `backup` blob from jobs/status.
 */

function formatBackupTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function plural(count, one, many) {
  return `${count} ${count === 1 ? one : many}`;
}

/** @returns {{line: string, error: string}|null} null when the server sent no backup blob. */
export function backupSummary(body) {
  const backup = body?.backup;
  if (!backup || typeof backup !== "object") return null;
  const error = typeof backup.last_error === "string" ? backup.last_error.trim() : "";
  const when = backup.last_backup ? formatBackupTime(backup.last_backup) : "";
  if (!when) return { line: "No backup yet", error };
  const daily = Number(backup.daily_count) || 0;
  const weekly = Number(backup.weekly_count) || 0;
  return {
    line: `Last backup ${when} · ${plural(daily, "daily", "dailies")}, ${plural(weekly, "weekly", "weeklies")} kept`,
    error,
  };
}
