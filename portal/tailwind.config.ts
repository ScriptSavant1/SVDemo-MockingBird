import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          primary: "#003875",
          secondary: "#00A9E0",
        },
      },
    },
  },
  plugins: [],
} satisfies Config;
