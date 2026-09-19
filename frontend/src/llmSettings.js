/** Multi-provider BYO LLM helpers for Settings (switch memory + recommended models). */

export const FALLBACK_PROVIDERS = [
  {
    id: "openai",
    label: "OpenAI",
    default_base_url: "https://api.openai.com/v1",
    key_url: "https://platform.openai.com/api-keys",
    key_help: "Create an API key in the OpenAI dashboard.",
    models: [
      { id: "gpt-4o-mini", label: "GPT-4o mini", recommended: true, note: "Best cost for lists & ranking" },
      { id: "gpt-4o", label: "GPT-4o", recommended: false, note: "Higher quality, higher cost" },
    ],
  },
  {
    id: "anthropic",
    label: "Anthropic",
    default_base_url: "https://api.anthropic.com",
    key_url: "https://console.anthropic.com/settings/keys",
    key_help: "Create an API key in the Anthropic console.",
    models: [
      { id: "claude-sonnet-4-5", label: "Claude Sonnet 4.5", recommended: true, note: "Strong default for household use" },
      { id: "claude-haiku-4-5", label: "Claude Haiku 4.5", recommended: false, note: "Faster / cheaper" },
    ],
  },
  {
    id: "gemini",
    label: "Google Gemini",
    default_base_url: "https://generativelanguage.googleapis.com/v1beta",
    key_url: "https://aistudio.google.com/apikey",
    key_help: "Create a Gemini API key in Google AI Studio.",
    models: [
      { id: "gemini-2.5-flash", label: "Gemini 2.5 Flash", recommended: true, note: "Fast and inexpensive — recommended" },
      { id: "gemini-2.5-pro", label: "Gemini 2.5 Pro", recommended: false, note: "Higher quality when you need it" },
    ],
  },
];

export function normalizeProviderId(value) {
  const text = String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, "_");
  if (["google", "google_gemini", "google_ai", "gemini_api"].includes(text)) return "gemini";
  if (["openai_compatible", "openai_compat", "compatible", "oai"].includes(text)) return "openai";
  if (text === "claude") return "anthropic";
  if (["openai", "anthropic", "gemini"].includes(text)) return text;
  return "openai";
}

export function providerCatalog(settings) {
  const rows = Array.isArray(settings?.llm_providers) && settings.llm_providers.length
    ? settings.llm_providers
    : FALLBACK_PROVIDERS;
  return rows.map((row) => ({
    ...row,
    id: normalizeProviderId(row.id),
  }));
}

export function recommendedModelFor(provider, catalog = FALLBACK_PROVIDERS) {
  const pid = normalizeProviderId(provider);
  const row = catalog.find((item) => item.id === pid) || FALLBACK_PROVIDERS.find((item) => item.id === pid);
  const models = row?.models || [];
  const hit = models.find((model) => model.recommended) || models[0];
  return hit?.id || "";
}

export function emptyProfile(provider, catalog = FALLBACK_PROVIDERS) {
  const pid = normalizeProviderId(provider);
  const row = catalog.find((item) => item.id === pid) || FALLBACK_PROVIDERS.find((item) => item.id === pid);
  return {
    base_url: row?.default_base_url || "",
    model: recommendedModelFor(pid, catalog),
    api_key: "",
    api_key_set: false,
    key_source: "",
  };
}

export function readProfiles(settings) {
  const catalog = providerCatalog(settings);
  const src = settings?.llm_profiles && typeof settings.llm_profiles === "object" ? settings.llm_profiles : {};
  const out = {};
  for (const row of catalog) {
    const raw = src[row.id] && typeof src[row.id] === "object" ? src[row.id] : {};
    const base = emptyProfile(row.id, catalog);
    out[row.id] = {
      base_url: String(raw.base_url || base.base_url || "").trim() || base.base_url,
      model: String(raw.model || base.model || "").trim() || base.model,
      api_key: String(raw.api_key || "").trim(),
      api_key_set: Boolean(raw.api_key_set) || Boolean(String(raw.api_key || "").trim()),
      key_source: String(raw.key_source || "").trim(),
    };
  }
  return out;
}

/** Snapshot active form fields into the provider profile (keeps unsaved key edits). */
export function stashActiveProfile(settings, profiles) {
  const provider = normalizeProviderId(settings?.llm_provider);
  const next = { ...profiles };
  const prev = next[provider] || emptyProfile(provider);
  const typedKey = String(settings?.llm_api_key || "").trim();
  next[provider] = {
    ...prev,
    base_url: String(settings?.llm_base_url || prev.base_url || "").trim() || prev.base_url,
    model: String(settings?.llm_model || prev.model || "").trim() || prev.model,
    api_key: typedKey,
    api_key_set: Boolean(typedKey) || Boolean(prev.api_key_set),
    key_source: typedKey ? "settings" : prev.key_source || "",
  };
  return next;
}

/** Switch provider: stash current, restore remembered profile, autofill recommended model when empty. */
export function switchProvider(settings, profiles, nextProvider, catalog) {
  const cat = catalog || providerCatalog(settings);
  const stashed = stashActiveProfile(settings, profiles);
  const pid = normalizeProviderId(nextProvider);
  const profile = stashed[pid] || emptyProfile(pid, cat);
  const model = String(profile.model || "").trim() || recommendedModelFor(pid, cat);
  return {
    settings: {
      ...settings,
      llm_provider: pid,
      llm_base_url: profile.base_url || emptyProfile(pid, cat).base_url,
      llm_model: model,
      llm_api_key: profile.api_key || "",
      llm_profiles: stashed,
    },
    profiles: {
      ...stashed,
      [pid]: { ...profile, model },
    },
  };
}

export function applyRecommendedModel(settings, catalog) {
  const cat = catalog || providerCatalog(settings);
  const model = recommendedModelFor(settings?.llm_provider, cat);
  return { ...settings, llm_model: model };
}

export function llmStatusCopy(settings) {
  const status = settings?.llm_status;
  if (status?.status_copy) return status.status_copy;
  if (settings?.llm_api_key_set || String(settings?.llm_api_key || "").trim()) {
    const source = settings?.llm_api_key_source === "env" ? " (from env)" : "";
    return `Ready — key saved${source}`;
  }
  return "Add an API key to enable list naming, Review suggest, and search ranking.";
}
