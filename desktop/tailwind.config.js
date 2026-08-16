const path = require('path')

// When '@product' points outside this project (COW_PRODUCT_DIR), scan that
// directory too so classes used only there still get generated.
const productContent = process.env.COW_PRODUCT_DIR
  ? [path.join(process.env.COW_PRODUCT_DIR, '**/*.{tsx,ts}')]
  : []

/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/renderer/**/*.{html,tsx,ts}', ...productContent],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        // Driven by CSS variables so a skin can restyle typography.
        sans: 'var(--font-sans)',
        mono: 'var(--font-mono)',
      },
      colors: {
        'danger-soft': 'var(--danger-soft)',
        'danger-border': 'var(--danger-border)',
        // Brand accent (kept for backward compat + explicit accent usage)
        primary: {
          50: '#EDFDF3',
          100: '#D4FAE2',
          200: '#ABF4C7',
          300: '#74E9A4',
          400: '#4ABE6E',
          500: '#35A85B',
          600: '#228547',
          700: '#1C6B3B',
          800: '#1A5532',
          900: '#16462A',
        },
        // Semantic tokens — driven by CSS variables, theme-aware
        accent: {
          DEFAULT: 'var(--accent)',
          hover: 'var(--accent-hover)',
          active: 'var(--accent-active)',
          soft: 'var(--accent-soft)',
          contrast: 'var(--accent-contrast)',
        },
        // User message bubble (theme-overridable, falls back to accent)
        'bubble-user': 'var(--bubble-user-bg)',
        'bubble-user-text': 'var(--bubble-user-text)',
        base: 'var(--bg-base)',
        surface: {
          DEFAULT: 'var(--bg-surface)',
          2: 'var(--bg-surface-2)',
        },
        elevated: 'var(--bg-elevated)',
        inset: 'var(--bg-inset)',
        content: {
          DEFAULT: 'var(--text-primary)',
          secondary: 'var(--text-secondary)',
          tertiary: 'var(--text-tertiary)',
          disabled: 'var(--text-disabled)',
        },
        success: 'var(--success)',
        warning: 'var(--warning)',
        danger: 'var(--danger)',
        info: 'var(--info)',
      },
      borderColor: {
        DEFAULT: 'var(--border-default)',
        default: 'var(--border-default)',
        strong: 'var(--border-strong)',
        subtle: 'var(--border-subtle)',
      },
      boxShadow: {
        sm: 'var(--shadow-sm)',
        md: 'var(--shadow-md)',
        lg: 'var(--shadow-lg)',
      },
      borderRadius: {
        card: 'var(--radius-card)',
        btn: 'var(--radius-btn)',
        sm: 'var(--radius-sm)',
      },
      animation: {
        'pulse-dot': 'pulseDot 1.4s infinite ease-in-out both',
      },
      keyframes: {
        pulseDot: {
          '0%, 80%, 100%': { transform: 'scale(0.6)', opacity: '0.4' },
          '40%': { transform: 'scale(1)', opacity: '1' },
        },
      },
    },
  },
  plugins: [],
}
