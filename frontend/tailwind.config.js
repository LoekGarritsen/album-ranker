/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'bg-primary': '#0A0E1A',
        'bg-secondary': '#121829',
        'accent-primary': '#1DB954',
        'accent-secondary': '#3B82F6',
        'accent-orange': '#F97316',
      },
      fontFamily: {
        heading: ['Outfit', 'sans-serif'],
        body: ['Work Sans', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
