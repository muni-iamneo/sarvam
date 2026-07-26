/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#241B33',
        muted: '#6F6A82',
        violet: { DEFAULT: '#6D4AE0', light: '#8B6FE8' },
        line: '#ECE7F8',
        tint: '#F7F4FE',
        'on-dark': '#E7E1F7',
        'on-dark-accent': '#C7B8FF',
        chart: { DEFAULT: '#6D4AE0', muted: '#CDBFF2' },
        brand: { hul: '#0A5AA8', colgate: '#D51A25', pg: '#00477B' },
      },
      fontFamily: {
        display: ['Spectral', 'Georgia', 'serif'],
        sans: ['Poppins', 'system-ui', 'sans-serif'],
      },
      borderRadius: { card: '16px', tile: '22px', chip: '8px', pill: '999px' },
      boxShadow: {
        soft: '0 6px 22px rgba(76,42,140,.12)',
        'soft-sm': '0 2px 8px rgba(76,42,140,.08)',
      },
      backgroundImage: {
        'grad-lavender': 'linear-gradient(135deg,#CBB6FF,#9A78F2)',
        'grad-periwinkle': 'linear-gradient(135deg,#BAC6FF,#7E8CEE)',
        'grad-violet': 'linear-gradient(135deg,#D9BBFF,#9A5CF0)',
        'grad-indigo': 'linear-gradient(135deg,#AEB8FF,#6D6AE6)',
      },
    },
  },
  plugins: [],
}
