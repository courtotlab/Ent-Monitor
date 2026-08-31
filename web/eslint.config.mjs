import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
  {
    rules: {
      // Known incompatibility with TanStack Table.
      "react-hooks/incompatible-library": "off",
      // Allow intentional synchronous setState calls (e.g., reset loading state).
      "react-hooks/set-state-in-effect": "off",
      // Keep as warning globally.
      "react-hooks/exhaustive-deps": "warn",
      // Allow var for global typescript declarations
      "no-var": "off",
    },
  },
  {
    // Spread deps [...deps, tick] in use-api are intentional and correct by design.
    files: ["src/hooks/use-api.ts"],
    rules: {
      "react-hooks/exhaustive-deps": "off",
    },
  },
]);

export default eslintConfig;

