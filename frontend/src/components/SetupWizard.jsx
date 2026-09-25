import { FIELD_HELP } from "../copy.js";
import { FieldLabel } from "./FieldHelp.jsx";

/** Field groups formerly stepped by the first-run wizard — now flat Settings panels. */
export const SETUP_STEPS = [
  {
    id: "downloader",
    kicker: "Downloader",
    title: "SABnzbd",
    lede: "Request queues here. URL and API key only.",
    fields: [
      ["sabnzbd_url", "SABnzbd URL"],
      ["sabnzbd_api_key", "SABnzbd API key", true],
    ],
  },
  {
    id: "indexers",
    kicker: "Indexers",
    title: "NZBFinder",
    lede: "Primary Newznab host for Find beyond the shelves. Token stays on this host.",
    fields: [
      ["nzbfinder_url", "NZBFinder URL"],
      ["nzbfinder_api_token", "NZBFinder token", true],
    ],
  },
  {
    id: "shelves",
    kicker: "Shelves",
    title: "Library roots",
    lede: "Where organized volumes land, usually under /data.",
    fields: [
      ["books_root", "Books root"],
      ["magazines_root", "Magazines root"],
      ["comics_root", "Comics root"],
      ["audiobooks_root", "Audiobooks root"],
      ["incoming_music_root", "Incoming music"],
      ["music_root", "Plexamp music"],
    ],
  },
  {
    id: "bagging",
    kicker: "Bagging",
    title: "Complete root",
    lede: "If SAB finishes at /downloads, map that path so Review can see files.",
    fields: [["complete_root", "SAB complete root"]],
  },
];

/** Render one setup field group (no Prev/Next chrome). */
export function SetupFields({ step, settings, onChange }) {
  const current = typeof step === "number" ? SETUP_STEPS[step] : SETUP_STEPS.find((row) => row.id === step);
  if (!current || !settings) return null;
  const stepId = current.id || "downloader";

  return (
    <section className="settings-panel" id={stepId} data-testid={`settings-panel-${stepId}`} aria-labelledby={`settings-${stepId}-heading`}>
      <p className="kicker" id={`settings-${stepId}-heading`}>
        {current.kicker}
      </p>
      <h2>{current.title}</h2>
      <p className="lede">{current.lede}</p>
      {current.fields.map(([key, label, secret]) => (
        <div key={key} className="field">
          <FieldLabel htmlFor={`setting-${key}`} label={label} help={FIELD_HELP[key]} />
          <input
            id={`setting-${key}`}
            type={secret ? "password" : "text"}
            value={settings[key] || ""}
            placeholder={secret && settings[`${key}_set`] ? "saved" : ""}
            onChange={(e) => onChange(key, e.target.value)}
          />
        </div>
      ))}
    </section>
  );
}

