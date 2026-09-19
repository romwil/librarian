import { FieldLabel } from "./FieldHelp.jsx";
import {
  applyRecommendedModel,
  llmStatusCopy,
  normalizeProviderId,
  providerCatalog,
  readProfiles,
  recommendedModelFor,
  stashActiveProfile,
  switchProvider,
} from "../llmSettings.js";

/**
 * Friendly BYO LLM panel — provider picker, recommended models, per-provider memory.
 * Keys never leave the form as plain text in status copy.
 */
export default function LlmSettingsPanel({ settings, onChange }) {
  const catalog = providerCatalog(settings);
  const provider = normalizeProviderId(settings?.llm_provider);
  const active = catalog.find((row) => row.id === provider) || catalog[0];
  const profiles = readProfiles(settings);
  const keySet = Boolean(settings?.llm_api_key_set) || Boolean(String(settings?.llm_api_key || "").trim());
  const keySource = settings?.llm_api_key_source || profiles[provider]?.key_source || "";
  const status = llmStatusCopy(settings);

  function patch(partial) {
    const next = { ...settings, ...partial };
    const profiles = stashActiveProfile(next, readProfiles(settings));
    onChange({ ...next, llm_profiles: profiles });
  }

  function onProviderChange(nextId) {
    const result = switchProvider(settings, profiles, nextId, catalog);
    onChange({ ...result.settings, llm_profiles: result.profiles });
  }

  function onModelChip(modelId) {
    patch({ llm_model: modelId });
  }

  function onRecommend() {
    onChange(applyRecommendedModel(settings, catalog));
  }

  return (
    <section className="llm-settings" data-testid="llm-settings">
      <header className="rail-head">
        <div>
          <h3 className="kicker">Language model</h3>
          <p className="lede">
            Optional BYO model for Bestsellers list naming, Review dump-name suggest, and ranking Find /
            chase hits. Native APIs for OpenAI, Anthropic, and Gemini — not shims.
          </p>
        </div>
      </header>

      <p className="muted" data-testid="llm-status" role="status">
        {status}
        {keySet && keySource === "env" ? " · key from environment" : null}
        {keySet && keySource === "settings" ? " · key saved in Settings" : null}
      </p>

      <div className="field">
        <FieldLabel htmlFor="setting-llm_provider" label="Provider" help="Switching remembers each provider’s key, model, and base URL." />
        <select
          id="setting-llm_provider"
          value={provider}
          onChange={(e) => onProviderChange(e.target.value)}
          data-testid="llm-provider"
        >
          {catalog.map((row) => (
            <option key={row.id} value={row.id}>
              {row.label}
            </option>
          ))}
        </select>
      </div>

      <div className="field">
        <FieldLabel
          htmlFor="setting-llm_api_key"
          label={`${active?.label || "Provider"} API key`}
          help={active?.key_help || "Paste the provider API key. Never invents an ISBN."}
        />
        <input
          id="setting-llm_api_key"
          type="password"
          value={settings.llm_api_key || ""}
          placeholder={keySet ? (keySource === "env" ? "from env" : "saved") : ""}
          onChange={(e) => patch({ llm_api_key: e.target.value })}
          autoComplete="off"
          data-testid="llm-api-key"
        />
        {active?.key_url ? (
          <p className="muted">
            <a href={active.key_url} target="_blank" rel="noreferrer">
              Get a {active.label} API key
            </a>
          </p>
        ) : null}
      </div>

      <div className="field">
        <FieldLabel htmlFor="setting-llm_model" label="Model" help="Recommended household defaults autofill when you switch provider." />
        <input
          id="setting-llm_model"
          value={settings.llm_model || ""}
          onChange={(e) => patch({ llm_model: e.target.value })}
          spellCheck={false}
          data-testid="llm-model"
        />
        <div className="chip-row" data-testid="llm-model-chips">
          {(active?.models || []).map((model) => (
            <button
              key={model.id}
              type="button"
              className={`chip${settings.llm_model === model.id ? " is-on" : ""}`}
              onClick={() => onModelChip(model.id)}
              title={model.note || model.label}
            >
              {model.label}
              {model.recommended ? " · recommended" : ""}
            </button>
          ))}
          <button type="button" className="chip" onClick={onRecommend} data-testid="llm-recommend">
            Use recommended ({recommendedModelFor(provider, catalog)})
          </button>
        </div>
      </div>

      <div className="field">
        <FieldLabel
          htmlFor="setting-llm_base_url"
          label="API base URL"
          help="Leave the default unless you use a proxy. Gemini and Anthropic use their native hosts — not OpenAI /v1/chat/completions."
        />
        <input
          id="setting-llm_base_url"
          value={settings.llm_base_url || ""}
          onChange={(e) => patch({ llm_base_url: e.target.value })}
          spellCheck={false}
          placeholder={active?.default_base_url || ""}
          data-testid="llm-base-url"
        />
      </div>
    </section>
  );
}
