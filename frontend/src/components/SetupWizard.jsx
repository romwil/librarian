import { FIELD_HELP, setupComplete } from "../copy.js";
import { FieldLabel } from "./FieldHelp.jsx";

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
    id: "indexer",
    kicker: "Indexer",
    title: "NZBFinder",
    lede: "Beyond the shelves. Token stays on this host.",
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

/** Household setup panel — section jump nav lives on SettingsPage. */
export default function SetupWizard({ settings, onChange, step, setStep }) {
  const current = SETUP_STEPS[step] || SETUP_STEPS[0];
  const done = setupComplete(settings);
  const stepId = current.id || "downloader";

  return (
    <section className="wizard" id="setup" aria-label="Household setup" data-setup-step={stepId}>
      <header className="wizard-head">
        <p className="kicker">{done ? "Setup complete" : "First-run steps"}</p>
      </header>
      <div className="wizard-panel card" id={stepId}>
        <p className="kicker">{current.kicker}</p>
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
        <div className="cta-row">
          {step > 0 ? (
            <button type="button" className="cta ghost" onClick={() => setStep(step - 1)}>
              Back
            </button>
          ) : null}
          {step < SETUP_STEPS.length - 1 ? (
            <button type="button" className="cta outline" onClick={() => setStep(step + 1)}>
              Next
            </button>
          ) : (
            <p className="muted">Save below when the path is right.</p>
          )}
        </div>
      </div>
    </section>
  );
}
