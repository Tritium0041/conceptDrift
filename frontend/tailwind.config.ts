import type { Config } from "tailwindcss";
import typography from "@tailwindcss/typography";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#18212f",
        mist: "#eef3f1",
        moss: "#2d6a4f",
        coral: "#e46f51",
        amber: "#d59f2f"
      },
      boxShadow: {
        soft: "0 16px 50px rgba(24, 33, 47, 0.08)"
      }
    }
  },
  plugins: [typography]
};

export default config;

