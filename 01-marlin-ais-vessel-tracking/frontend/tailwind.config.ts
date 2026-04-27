import type { Config } from 'tailwindcss';

export default {
  content: ['./app/**/*.{js,ts,jsx,tsx}', './components/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        kw: {
          primary: '#00BB7A',
          hover: '#0DCC8A',
          neon: '#00FFA7',
          deep: '#065238',
          bg: '#0A0A0A',
          surface: '#0E0E0E',
          surfaceHi: '#111111',
          border: '#222222',
          muted: '#6A6969',
          dim: '#7E7E7E',
        },
      },
      fontFamily: {
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
    },
  },
  plugins: [],
} satisfies Config;
