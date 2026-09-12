import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        jarvis: {
          bg: "#0a0b0f",
          panel: "#12141c",
          panel2: "#191c27",
          border: "#262a3a",
          accent: "#5b8cff",
          accent2: "#8b5bff",
          glow: "#5b8cff33",
          ok: "#35c186",
          err: "#ff5d6c",
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
      },
      keyframes: {
        pulseGlow: {
          "0%, 100%": { opacity: "0.5", transform: "scale(1)" },
          "50%": { opacity: "1", transform: "scale(1.08)" },
        },
        rise: {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        pulseGlow: "pulseGlow 1.6s ease-in-out infinite",
        rise: "rise 0.25s ease-out",
      },
    },
  },
  plugins: [],
};

export default config;
