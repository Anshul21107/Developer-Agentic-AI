/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        display: ["\"Space Grotesk\"", "system-ui", "sans-serif"],
        body: ["\"IBM Plex Sans\"", "system-ui", "sans-serif"]
      }
    }
  },
  plugins: []
};
