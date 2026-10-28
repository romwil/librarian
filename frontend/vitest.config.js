import { fileURLToPath } from "node:url";
import { defineConfig, mergeConfig } from "vitest/config";
import viteConfig from "./vite.config.js";

export default mergeConfig(
  viteConfig,
  defineConfig({
    resolve: {
      alias: {
        // review.test.js still imports node:test; it maps onto Vitest's runner.
        "node:test": fileURLToPath(new URL("./src/test/nodeTestShim.js", import.meta.url)),
      },
    },
    test: {
      include: ["src/**/*.test.{js,jsx}"],
      environment: "node",
      setupFiles: ["./src/test/setup.js"],
    },
  }),
);
