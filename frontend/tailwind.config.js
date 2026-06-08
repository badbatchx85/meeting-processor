import typography from "@tailwindcss/typography";

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        display: ['"Bricolage Grotesque Variable"', "ui-sans-serif", "sans-serif"],
        sans: ['"Hanken Grotesk Variable"', "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono Variable"', "ui-monospace", "monospace"],
      },
      colors: {
        // Warm-neutral "newsprint" system: stone paper + near-black ink.
        paper: "#FAFAF9",
        surface: "#FFFFFF",
        ink: { DEFAULT: "#0A0A0A", soft: "#1C1917" },
        line: { DEFAULT: "#E7E5E4", soft: "#F0EFEC" },
        muted: { DEFAULT: "#78716C", soft: "#A8A29E" },
        // `brand` kept as an alias so existing `*-brand` utilities resolve to ink.
        brand: { DEFAULT: "#0A0A0A", dark: "#000000" },
      },
      letterSpacing: {
        tightest: "-0.04em",
        label: "0.18em",
      },
      boxShadow: {
        card: "0 1px 2px rgba(28,25,23,0.04), 0 1px 1px rgba(28,25,23,0.03)",
        lift: "0 18px 40px -16px rgba(28,25,23,0.22)",
      },
      borderRadius: {
        card: "14px",
      },
    },
  },
  plugins: [typography],
};
