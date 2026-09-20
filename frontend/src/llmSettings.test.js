import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  applyRecommendedModel,
  normalizeProviderId,
  recommendedModelFor,
  stashActiveProfile,
  switchProvider,
} from "./llmSettings.js";

describe("llmSettings provider memory", () => {
  it("normalizes openai_compatible and google aliases", () => {
    assert.equal(normalizeProviderId("openai_compatible"), "openai");
    assert.equal(normalizeProviderId("Google"), "gemini");
  });

  it("recommends household defaults", () => {
    assert.equal(recommendedModelFor("openai"), "gpt-4o-mini");
    assert.match(recommendedModelFor("gemini"), /gemini/);
    assert.match(recommendedModelFor("anthropic"), /claude/);
  });

  it("remembers keys when switching providers and autofills recommended model", () => {
    const start = {
      llm_provider: "openai",
      llm_api_key: "sk-openai",
      llm_model: "gpt-4o",
      llm_base_url: "https://api.openai.com/v1",
      llm_profiles: {},
    };
    const profiles = stashActiveProfile(start, {});
    const toGemini = switchProvider(start, profiles, "gemini");
    assert.equal(toGemini.settings.llm_provider, "gemini");
    assert.match(toGemini.settings.llm_model, /gemini/);
    assert.equal(toGemini.profiles.openai.api_key, "sk-openai");

    // Type a gemini key, switch back — openai key restored
    const withGem = {
      ...toGemini.settings,
      llm_api_key: "gem-key",
      llm_model: "gemini-3.6-flash",
    };
    const back = switchProvider(withGem, toGemini.profiles, "openai");
    assert.equal(back.settings.llm_provider, "openai");
    assert.equal(back.settings.llm_api_key, "sk-openai");
    assert.equal(back.profiles.gemini.api_key, "gem-key");
  });

  it("applyRecommendedModel fills the recommended id", () => {
    const next = applyRecommendedModel({ llm_provider: "gemini", llm_model: "gemini-2.5-flash" });
    assert.equal(next.llm_model, "gemini-3.6-flash");
  });
});
