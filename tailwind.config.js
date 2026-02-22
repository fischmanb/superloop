/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: { DEFAULT: '#3B82F6', hover: '#2563EB', light: '#DBEAFE' },
        secondary: { DEFAULT: '#8B5CF6', hover: '#7C3AED', light: '#EDE9FE' },
        surface: { DEFAULT: '#F9FAFB', elevated: '#FFFFFF' },
        success: { DEFAULT: '#10B981', light: '#D1FAE5' },
        warning: { DEFAULT: '#F59E0B', light: '#FEF3C7' },
        error: { DEFAULT: '#EF4444', light: '#FEE2E2' },
        info: { DEFAULT: '#06B6D4', light: '#CFFAFE' },
      },
    },
  },
  plugins: [],
}
