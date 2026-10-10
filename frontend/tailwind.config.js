/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#eef2ff',
          100: '#e0e7ff',
          200: '#c7d2fe',
          300: '#a5b4fc',
          400: '#818cf8',
          500: '#6478f5',
          600: '#4f46e5',
          700: '#4338ca',
          800: '#3730a3',
          900: '#312e81',
          950: '#1e1b4b',
        },
        pastel: {
          blue: '#e8f0ff',
          lavender: '#f0ebff',
          mint: '#e3f8ef',
          cyan: '#e4f7fb',
          amber: '#fef3c7',
          rose: '#ffe4e6',
        },
      },
      boxShadow: {
        'glass': '0 4px 20px -2px rgba(100, 116, 139, 0.07), 0 2px 6px -1px rgba(100, 116, 139, 0.04)',
        'glass-hover': '0 8px 28px -4px rgba(100, 116, 139, 0.12), 0 4px 10px -2px rgba(100, 116, 139, 0.06)',
        'glass-modal': '0 20px 40px -8px rgba(15, 23, 42, 0.15), 0 8px 16px -4px rgba(15, 23, 42, 0.08)',
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'Menlo', 'Monaco', 'Courier New', 'monospace'],
        sans: ['Inter', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
