/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: '#25262b',
          border: '#373a40',
          muted: '#495057',
        },
        panel: '#1e1e1e',
        accent: '#74c0fc',
        danger: '#fa5252',
        muted: '#868e96',
      },
    },
  },
  plugins: [],
}
