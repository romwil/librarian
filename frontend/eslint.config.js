import js from "@eslint/js";
import prettier from "eslint-config-prettier";
import jsxA11y from "eslint-plugin-jsx-a11y";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";

export default [
  { ignores: ["dist/**", "node_modules/**", "test-results/**", "coverage/**", "public/**"] },
  js.configs.recommended,
  {
    files: ["**/*.{js,jsx}"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      parserOptions: { ecmaFeatures: { jsx: true } },
      globals: { ...globals.browser },
    },
    settings: { react: { version: "detect" } },
    plugins: { react, "react-hooks": reactHooks, "jsx-a11y": jsxA11y },
    rules: {
      ...react.configs.recommended.rules,
      ...react.configs["jsx-runtime"].rules,
      ...reactHooks.configs.recommended.rules,
      ...jsxA11y.flatConfigs.recommended.rules,
      // In-app <audio> is playback, not captioned video.
      "jsx-a11y/media-has-caption": "off",
      // Modal titles and skip targets use tabIndex={-1} so VO/keyboard can land on them.
      "jsx-a11y/no-noninteractive-tabindex": "off",
      "react/prop-types": "off",
      // Warn, not error, until the pre-lint backlog in shared modules is groomed.
      "no-unused-vars": ["warn", { argsIgnorePattern: "^_", caughtErrors: "none" }],
      "no-useless-escape": "warn",
      "no-extra-boolean-cast": "warn",
    },
  },
  {
    files: ["**/*.test.{js,jsx}", "src/test/**", "*.config.js"],
    languageOptions: { globals: { ...globals.node } },
  },
  prettier,
];
