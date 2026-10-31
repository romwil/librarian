import { describe, expect, it } from "vitest";
import {
  indexerBudgetCaption,
  indexerBudgetHosts,
  pollerStepCaption,
} from "./indexerBudget.js";

describe("indexerBudget", () => {
  it("reads household host totals and never looks for a user id", () => {
    const hosts = indexerBudgetHosts({
      indexer_budget: {
        day: "2026-10-31",
        hosts: [
          {
            id: "nzbfinder",
            name: "NZBFinder",
            calls: 12,
            wanted_calls: 8,
            budget: 500,
            wanted_budget: 250,
          },
        ],
      },
    });
    expect(hosts).toHaveLength(1);
    expect(indexerBudgetCaption(hosts[0])).toBe("NZBFinder · 12 / 500 (Wanted 8 / 250)");
    expect(JSON.stringify(hosts[0])).not.toMatch(/user_id|username|reader/);
  });

  it("labels disabled poller steps as Off", () => {
    expect(
      pollerStepCaption({
        id: "abs",
        label: "Audiobookshelf",
        state: "off",
        off_reason: "Off: not configured",
      }),
    ).toBe("Audiobookshelf · Off: not configured");
    expect(pollerStepCaption({ id: "owned", label: "Owned slips", state: "off" })).toBe(
      "Owned slips · Off: not configured",
    );
  });
});
