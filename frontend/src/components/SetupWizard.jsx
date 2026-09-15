import { FIELD_HELP, setupComplete, setupStepComplete } from "../copy.js";
import { FieldLabel } from "./FieldHelp.jsx";

const STEPS = [
  {
    kicker: "Downloader",
    title: "SABnzbd",
    lede: "Request queues here. URL and API key only.",
    fields: [
      ["sabnzbd_url", "SABnzbd URL"],
      ["sabnzbd_api_key", "SABnzbd API key", true],
    ],
  },
  {
    kicker: "Indexer",
    title: "NZBFinder",
    lede: "Beyond the shelves. Token stays on this host.",
    fields: [
      ["nzbfinder_url", "NZBFinder URL"],
      ["nzbfinder_api_token", "NZBFinder token", true],
    ],
  },
  {
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
    kicker: "Bagging",
    title: "Complete root",
    lede: "If SAB finishes at /downloads, map that path so Review can see files.",
    fields: [["complete_root", "SAB complete root"]],
  },
];

export default function SetupWizard({ settings, onChange, step, setStep }) {
  const current = STEPS[step] || STEPS[0];
  const done = setupComplete(settings);

  return (
    <section className="wizard" aria-label="Household setup">
      <header className="wizard-head">
        <p className="kicker">{done ? "Setup complete" : "First-run steps"}</p>
        <ol className="wizard-steps">
          {STEPS.map((item, index) => (
            <li key={item.title}>
              <button
                type="button"
                className={`wizard-step${index === step ? " is-on" : ""}${setupStepComplete(settings, index) ? " is-done" : ""}`}
                onClick={() => setStep(index)}
              >
                {index + 1}. {item.kicker}
              </button>
            </li>
          ))}
        </ol>
      </header>
      <div className="wizard-panel card">
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
          {step < STEPS.length - 1 ? (
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
