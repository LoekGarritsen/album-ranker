/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Spotify-style surface scale: elevation = lighter, never shadows
        'surface-base': '#000000',
        'bg-primary': '#121212',
        'bg-secondary': '#181818',
        'surface-highlight': '#242424',
        'surface-elevated': '#282828',
        'text-subdued': '#b3b3b3',
        'accent-primary': '#1DB954',
        'accent-bright': '#1ed760',
        'accent-secondary': '#3B82F6',
        'accent-orange': '#F97316',
      },
      fontFamily: {
        heading: ['Outfit', 'sans-serif'],
        body: ['Outfit', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
