import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{vue,ts}'],
  theme: {
    extend: {
      colors: {
        background: '#101214',
        panel: '#171a1d',
        panel2: '#202428',
        border: '#32383e',
        accent: '#7dd3fc',
        gain: '#48c78e',
        loss: '#ff6b6b'
      }
    }
  },
  plugins: []
} satisfies Config
