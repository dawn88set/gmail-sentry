/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
    // Include the widget toolkit's compiled output so its (liquid-glass)
    // className strings aren't purged when an app imports its components.
    "./node_modules/@clarittyai/widget-toolkit/dist/**/*.js",
    // The app-level kit (Dashboards/lists/forms) — same reason: keep its
    // token classes from being purged.
    "./node_modules/@clarittyai/app-ui/dist/**/*.js",
  ],
  darkMode: 'class',
  theme: {
    screens: {
      'sm': '640px',
      'md': '920px',
      'lg': '1024px',
      'xl': '1280px',
      '2xl': '1536px',
    },
    extend: {
      colors: {
        // Brand colors — driven by CSS variables so each generated app gets a
        // unique theme (defaults live in src/index.css :root; per-app values
        // are injected into src/theme.css at generation time). HSL channels +
        // <alpha-value> so opacity utilities (bg-primary/10) keep working.
        primary: {
          DEFAULT: 'hsl(var(--brand-primary) / <alpha-value>)',
          50: '#F9FAFB',
          100: '#F3F4F6',
          200: '#E5E7EB',
          300: '#D1D5DB',
          400: '#9CA3AF',
          500: '#6B7280',
          600: '#4B5563',
          700: '#374151',
          800: '#1F2937',
          900: '#111827',
          950: '#000000',
          foreground: '#FFFFFF',
        },
        // Accent — the app's primary brand color (theme-driven).
        accent: {
          DEFAULT: 'hsl(var(--brand-accent) / <alpha-value>)',
          50: '#EEF2FF',
          100: '#E0E7FF',
          200: '#C7D2FE',
          300: '#A5B4FC',
          400: '#818CF8',
          500: '#5B7FFF',
          600: 'hsl(var(--brand-accent-600) / <alpha-value>)',
          700: '#4338CA',
          800: '#3730A3',
          900: '#312E81',
          // Text/icon ON the accent fill. Theme-driven (CSS var, not static
          // white) so it flips to a dark tone in dark mode where the accent is
          // lightened — keeps the kit's primary Button label AA in both themes.
          foreground: 'hsl(var(--brand-accent-foreground) / <alpha-value>)',
        },
        // TOKEN LOCKDOWN: the saturated brand-conflicting ramps
        // (orange/purple/green/pink/teal/yellow) were removed so a generated
        // app can't reach for an off-theme accent — color comes ONLY from the
        // app's own theme tokens (accent/primary + the semantic slots below)
        // and the default neutral ramp. Status uses success/warning/destructive.
        // Existing shadcn/ui colors (kept for compatibility)
        // <alpha-value> on EVERY token so opacity utilities (bg-card/50,
        // bg-muted/8, border-border/40, …) actually render their tint instead of
        // silently dropping the opacity → flat surfaces. The vars are HSL channels
        // (same as accent above), so the alpha slot is valid.
        border: "hsl(var(--border) / <alpha-value>)",
        input: "hsl(var(--input) / <alpha-value>)",
        ring: "hsl(var(--ring) / <alpha-value>)",
        background: "hsl(var(--background) / <alpha-value>)",
        foreground: "hsl(var(--foreground) / <alpha-value>)",
        secondary: {
          DEFAULT: "hsl(var(--secondary) / <alpha-value>)",
          foreground: "hsl(var(--secondary-foreground) / <alpha-value>)",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive) / <alpha-value>)",
          foreground: "hsl(var(--destructive-foreground) / <alpha-value>)",
        },
        muted: {
          DEFAULT: "hsl(var(--muted) / <alpha-value>)",
          foreground: "hsl(var(--muted-foreground) / <alpha-value>)",
        },
        card: {
          DEFAULT: "hsl(var(--card) / <alpha-value>)",
          foreground: "hsl(var(--card-foreground) / <alpha-value>)",
        },
        success: {
          DEFAULT: '#34C759',
          foreground: '#FFFFFF',
        },
        warning: {
          DEFAULT: '#FF9500',
          foreground: '#FFFFFF',
        },
        // Gmail's four brand hues — kept for the mark / optional semantics.
        gmail: {
          blue: { 50: '#E8F0FE', 100: '#D2E3FC', 500: '#1A73E8', 600: '#1967D2', 700: '#174EA6' },
          red: { 50: '#FCE8E6', 100: '#FAD2CF', 500: '#EA4335', 600: '#D93025', 700: '#B31412' },
          yellow: { 50: '#FEF7E0', 100: '#FEEFC3', 500: '#FBBC04', 600: '#F9AB00', 700: '#E37400' },
          green: { 50: '#E6F4EA', 100: '#CEEAD6', 500: '#34A853', 600: '#1E8E3E', 700: '#0D652D' },
        },
        // Slack brand colors (for the official "Add to Slack" mark).
        slack: {
          blue: '#36C5F0',
          green: '#2EB67D',
          yellow: '#ECB22E',
          red: '#E01E5A',
        },
        // Gmail-style initial-avatar colors — solid, white-legible circles.
        av: {
          blue: '#1A73E8',
          teal: '#00897B',
          indigo: '#5C6BC0',
          purple: '#8E24AA',
          pink: '#D81B60',
          green: '#0F9D58',
          red: '#D93025',
          brown: '#795548',
        },
      },
      fontFamily: {
        // Theme-driven: --brand-font holds the full stack (default in index.css).
        sans: ['var(--brand-font)'],
        mono: ['SF Mono', 'Monaco', 'Cascadia Code', 'Roboto Mono', 'monospace'],
      },
      backgroundImage: {
        'gradient-radial': 'radial-gradient(var(--tw-gradient-stops))',
        'gradient-conic': 'conic-gradient(from 180deg at 50% 50%, var(--tw-gradient-stops))',
        // 'gradient-mesh' (multi-stop rainbow) removed by the style lockdown.
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
        'xl': '1rem',
        '2xl': '1.5rem',
        '3xl': '2rem',
        '4xl': '2.5rem',
      },
      boxShadow: {
        'glass': '0 8px 32px 0 rgba(31, 38, 135, 0.1)',
        'lift': '0 10px 40px -10px rgba(0, 0, 0, 0.1)',
        'lift-lg': '0 20px 60px -15px rgba(0, 0, 0, 0.15)',
        // Apple-style soft elevation — diffuse, low-contrast, layered.
        'apple': '0 1px 2px rgba(0,0,0,0.04), 0 8px 24px -8px rgba(0,0,0,0.10)',
        'apple-lg': '0 2px 4px rgba(0,0,0,0.04), 0 24px 48px -16px rgba(0,0,0,0.16)',
      },
      animation: {
        // Subtle entrance motion only. The looping `float`/`glow` (decorative
        // "AI tell") were removed as part of the token/style lockdown.
        'slide-up': 'slideUp 0.5s ease-out',
        'slide-down': 'slideDown 0.5s ease-out',
        'fade-in': 'fadeIn 0.5s ease-out',
        'scale-in': 'scaleIn 0.5s ease-out',
      },
      keyframes: {
        slideUp: {
          '0%': { transform: 'translateY(20px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        slideDown: {
          '0%': { transform: 'translateY(-20px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        scaleIn: {
          '0%': { transform: 'scale(0.95)', opacity: '0' },
          '100%': { transform: 'scale(1)', opacity: '1' },
        },
      },
    },
  },
  plugins: [],
}
