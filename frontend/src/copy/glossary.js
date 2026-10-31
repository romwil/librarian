/** One household glossary. Feeds in-app Help, HELP.md, and e2e lexicon checks. */

export const GLOSSARY = [
  {
    term: "Hall",
    meaning: "The front of the library after you sign in. Continue, arrivals, and a search that starts on the shelves.",
    audience: "reader",
  },
  {
    term: "Search",
    meaning: "Looks at what the house already owns first. Beyond the shelves is a later door.",
    audience: "reader",
  },
  {
    term: "Ask the house",
    meaning: "A reader’s request for a missing title. A keeper still confirms before anything is fetched.",
    audience: "reader",
  },
  {
    term: "Wanted",
    meaning: "Titles the house is looking for. Asked stays looking; Arrived means it is on the shelf.",
    audience: "reader",
  },
  {
    term: "Library card",
    meaning: "Your personal door: theme, text size, inbox, asks, export, and the OPDS catalog link.",
    audience: "reader",
  },
  {
    term: "Continue",
    meaning: "Where you left off — only after real reading or listening, not by opening a page.",
    audience: "reader",
  },
  {
    term: "Arrived",
    meaning: "Something you asked for has been filed on the shelves.",
    audience: "reader",
  },
  {
    term: "Inbox",
    meaning: "In-app notices. Arrival notes and asked-confirm live here; email is optional.",
    audience: "reader",
  },
  {
    term: "Sorting",
    meaning: "The owner desk at /review. Slips wait here. It is not a reader reservation.",
    audience: "owner",
  },
  {
    term: "Slip",
    meaning: "One Sorting item that needs identity or folder help before it can be filed.",
    audience: "owner",
  },
  {
    term: "Downloads",
    meaning: "The queue of fetches. Confirm is the only way SABnzbd starts.",
    audience: "owner",
  },
  {
    term: "Confirm",
    meaning: "The keeper step before a download. Product control — not a legal review.",
    audience: "owner",
  },
  {
    term: "Beyond the shelves",
    meaning: "Indexer search outside what the house already owns. Readers opt in with Ask the house.",
    audience: "owner",
  },
  {
    term: "Maintain",
    meaning: "Owner grooming: scan, enrich, backup, House pulse, shelf health. Credentials stay in Settings.",
    audience: "owner",
  },
  {
    term: "House pulse",
    meaning: "On-box household totals. Member reading figures hide until three people have a card. No analytics SDK.",
    audience: "owner",
  },
  {
    term: "OPDS",
    meaning: "A catalog link for e-reader apps. Copy it from the Library card. It lasts 180 days.",
    audience: "reader",
  },
];

export function glossaryForRole(role) {
  const cleaned = String(role || "reader").trim().toLowerCase() || "reader";
  if (cleaned === "owner" || cleaned === "op") return GLOSSARY.slice();
  return GLOSSARY.filter((row) => row.audience === "reader");
}

export function glossaryMarkdownTable(rows = GLOSSARY) {
  const lines = ["| Prefer | Meaning |", "| --- | --- |"];
  for (const row of rows) {
    lines.push(`| **${row.term}** | ${row.meaning} |`);
  }
  return `${lines.join("\n")}\n`;
}
