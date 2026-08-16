// ============================================================
// Theme Contract — single source of truth for themes.
//
// A "theme" is pure data: it overrides semantic design tokens
// (colors, radius, shadow, font) and an optional background
// wallpaper. It never touches component code or DOM structure,
// so themes stay stable across UI refactors — as long as
// components keep consuming these tokens, old themes keep working.
//
// Contract rule: themes may ONLY set fields defined here. Adding a
// new token is an additive, versioned change (bump THEME_SPEC_VERSION).
//
// Themes are NOT bundled into the app. They live in ~/.cow/themes/<id>/
// (theme.json + images) and are loaded at runtime via the main process,
// which inlines images as data URLs. The only built-in theme is 'default'
// (a pure-color fallback that always works offline).
// ============================================================

// ---- Color tokens (per-appearance) -------------------------
export const COLOR_KEYS = [
  'accent',
  'accentHover',
  'accentActive',
  'accentSoft',
  'accentContrast',
  'bubbleUserBg',
  'bubbleUserText',
  'bgBase',
  'bgSurface',
  'bgSurface2',
  'bgElevated',
  'bgInset',
  'textPrimary',
  'textSecondary',
  'textTertiary',
  'textDisabled',
  'borderDefault',
  'borderStrong',
  'borderSubtle',
  'shadowSm',
  'shadowMd',
  'shadowLg',
] as const
export type ColorKey = (typeof COLOR_KEYS)[number]

// ---- Shape tokens (appearance-independent) -----------------
// Radius / font apply regardless of light or dark.
export const SHAPE_KEYS = ['radiusCard', 'radiusBtn', 'radiusSm', 'fontSans', 'fontMono'] as const
export type ShapeKey = (typeof SHAPE_KEYS)[number]

// camelCase token -> --kebab-case CSS variable
export function tokenToCssVar(key: string): string {
  return '--' + key.replace(/[A-Z0-9]/g, (m) => '-' + m.toLowerCase())
}

// ---- Wallpaper (Codex-style ambient background) ------------
export interface Wallpaper {
  // Image URL (bundled asset path or data/file URL). Empty = solid color.
  image?: string
  focusX?: number // 0..1 horizontal focal point, default 0.5
  focusY?: number // 0..1 vertical focal point, default 0.5
  overlayOpacity?: number // 0..1 scrim strength over the image, default per-appearance
  // Panels become translucent + blurred (frosted glass) so the wallpaper
  // shows through. When false, panels stay solid (wallpaper only behind base).
  glass?: boolean
}

export interface ThemeAppearance {
  colors?: Partial<Record<ColorKey, string>>
  wallpaper?: Wallpaper
}

// Optional per-theme identity overrides (logo + display name).
export interface ThemeIdentity {
  logo?: string // data URL (inlined by main) or asset URL
  appName?: string
}

export interface Theme {
  id: string
  name: string
  specVersion?: number
  // Optional preview swatch; when absent it's derived from colors.
  preview?: { accent: string; bg: string; surface: string }
  identity?: ThemeIdentity
  // Appearance-independent shape tokens.
  shape?: Partial<Record<ShapeKey, string>>
  // Per-appearance colors + wallpaper.
  light?: ThemeAppearance
  dark?: ThemeAppearance
}

// Bump when the contract changes in a breaking way. theme.json files declare
// which version they target so imports can be validated.
export const THEME_SPEC_VERSION = 1

// 'default' uses the built-in :root / .dark values in index.css and
// applies no data-theme attribute nor overrides.
export const DEFAULT_THEME_ID = 'default'

// The only built-in theme: 'default' maps to the base :root / .dark values in
// index.css (no overrides). Everything else is loaded at runtime from
// ~/.cow/themes. This keeps the app bundle free of theme assets.
export const DEFAULT_THEME: Theme = {
  id: DEFAULT_THEME_ID,
  name: 'Meadow',
  preview: { accent: '#4abe6e', bg: '#f9fafb', surface: '#ffffff' },
}

// Runtime registry: default first, then whatever was loaded from ~/.cow.
let runtimeThemes: Theme[] = [DEFAULT_THEME]

// Basic shape validation so a malformed theme.json can't break the app.
function isValidTheme(x: unknown): x is Theme {
  if (!x || typeof x !== 'object') return false
  const s = x as Record<string, unknown>
  return typeof s.id === 'string' && s.id.length > 0
}

// Derive a preview swatch from a theme's colors when it didn't ship one.
function derivePreview(theme: Theme): { accent: string; bg: string; surface: string } {
  if (theme.preview) return theme.preview
  const c = theme.dark?.colors ?? theme.light?.colors ?? {}
  return {
    accent: c.accent ?? '#4abe6e',
    bg: c.bgBase ?? '#111111',
    surface: c.bgSurface ?? '#1c1c1f',
  }
}

// Replace the runtime theme list with default + validated remote themes.
export function registerRuntimeThemes(themes: unknown[]): void {
  const valid = (themes ?? []).filter(isValidTheme).filter((t) => t.id !== DEFAULT_THEME_ID)
  for (const t of valid) t.preview = derivePreview(t)
  runtimeThemes = [DEFAULT_THEME, ...valid]
}

export function getAllThemes(): Theme[] {
  return runtimeThemes
}

export function getTheme(id: string): Theme {
  return runtimeThemes.find((t) => t.id === id) ?? runtimeThemes[0]
}
