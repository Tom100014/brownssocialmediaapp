import type { Config } from "tailwindcss";
import plugin from "tailwindcss/plugin";

// Black Card Protocol design system
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: "#0A0A0A", // Obsidian
        primary: { DEFAULT: "#D4AF37", dark: "#9C7F1F", light: "#F2D675" }, // Gold
        secondary: "#1F1F1F",
      },
    },
  },
  plugins: [
    plugin(({ addUtilities }) => {
      addUtilities({
        ".glass": {
          "background-color": "rgba(31, 31, 31, 0.55)",
          "backdrop-filter": "blur(16px)",
          "-webkit-backdrop-filter": "blur(16px)",
          border: "1px solid rgba(212, 175, 55, 0.18)",
        },
      });
    }),
  ],
};

export default config;
