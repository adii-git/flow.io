import type { Config } from "tailwindcss";
// Tokens from the Phase 1 design system; values live in CSS variables so light/dark switch in one place.
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)", panel: "var(--panel)", sunk: "var(--sunk)", ink: "var(--ink)",
        mute: "var(--mute)", line: "var(--line)", acc: "var(--acc)", accink: "var(--accInk)", ok: "var(--ok)", bad: "var(--bad)",
      },
      fontFamily: { sans: ['"Bricolage Grotesque"', "system-ui", "sans-serif"] },
      borderRadius: { panel: "22px 22px 22px 6px", input: "12px", action: "10px 10px 10px 3px" },
    },
  },
};
export default config;
