/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html", "./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      colors: {
        grab: "#00B14F",      // Grab green
        "grab-bg": "#0a0f0d", // dark background
        "grab-card": "#141a17",
        "grab-edge": "#1f3d31"
      },
      boxShadow: {
        grab: "0 0 12px rgba(0, 177, 79, 0.35)"
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"]
      }
    }
  },
  plugins: []
};
