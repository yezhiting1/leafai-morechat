import { useState, useEffect, useCallback } from 'react'
import {
  COLOR_KEYS,
  DEFAULT_THEME_ID,
  getAllThemes,
  getTheme,
  registerRuntimeThemes,
  SHAPE_KEYS,
  tokenToCssVar,
  type Theme,
  type Wallpaper,
} from '../theme/themes'

export type ThemePref = 'light' | 'dark' | 'system'
export type ResolvedTheme = 'light' | 'dark'

// Appearance preference (light/dark/system).
const PREF_KEY = 'cow_theme'
// Selected theme id (which visual theme is active).
const THEME_ID_KEY = 'cow_theme_id'

function getSystemTheme(): ResolvedTheme {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function readStoredPref(): ThemePref {
  const saved = localStorage.getItem(PREF_KEY)
  if (saved === 'dark' || saved === 'light' || saved === 'system') return saved
  // First run: follow the OS appearance rather than forcing a fixed theme.
  return 'system'
}

function readStoredThemeId(): string {
  return localStorage.getItem(THEME_ID_KEY) || DEFAULT_THEME_ID
}

// Whether the user has ever explicitly chosen a theme. Used so a bundled
// first-run default only applies when the user hasn't made a choice yet.
function hasStoredThemeId(): boolean {
  return localStorage.getItem(THEME_ID_KEY) != null
}

// All CSS variables a theme may inject, so we can fully reset before
// applying one (prevents stale overrides from leaking across switches).
const WALLPAPER_VARS = [
  '--wallpaper-image',
  '--wallpaper-position',
  '--wallpaper-overlay',
  '--glass-fill',
  '--glass-blur',
  '--surface-alpha',
] as const

function hexToRgb(hex: string): [number, number, number] | null {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim())
  if (!m) return null
  const n = parseInt(m[1], 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

// Apply the resolved appearance (light/dark) as the .dark class, plus the
// active theme's overrides. Themes are pure data: we only write contract
// tokens as inline CSS variables on <html> (and toggle a wallpaper flag on
// <body>), so components restyle without any code change.
function applyAppearanceAndTheme(resolved: ResolvedTheme, themeId: string) {
  const root = document.documentElement
  root.classList.toggle('dark', resolved === 'dark')

  const theme = getTheme(themeId)
  if (theme.id === DEFAULT_THEME_ID) root.removeAttribute('data-theme')
  else root.setAttribute('data-theme', theme.id)

  activeSurface = {
    light: theme.light?.colors?.bgSurface,
    dark: theme.dark?.colors?.bgSurface,
  }

  // Reset everything a theme can touch, then re-apply the active one.
  for (const key of COLOR_KEYS) root.style.removeProperty(tokenToCssVar(key))
  for (const key of SHAPE_KEYS) root.style.removeProperty(tokenToCssVar(key))
  for (const v of WALLPAPER_VARS) root.style.removeProperty(v)

  // Shape tokens are appearance-independent.
  if (theme.shape) {
    for (const [k, v] of Object.entries(theme.shape)) {
      if (v) root.style.setProperty(tokenToCssVar(k), v)
    }
  }

  const appearance = resolved === 'dark' ? theme.dark : theme.light
  if (appearance?.colors) {
    for (const [k, v] of Object.entries(appearance.colors)) {
      if (v) root.style.setProperty(tokenToCssVar(k), v)
    }
  }

  applyWallpaper(resolved, appearance?.wallpaper)
}

// Render (or clear) the ambient wallpaper + frosted-glass panels.
function applyWallpaper(resolved: ResolvedTheme, wp?: Wallpaper) {
  const root = document.documentElement
  const body = document.body
  if (!wp?.image) {
    body.removeAttribute('data-wallpaper')
    return
  }
  body.setAttribute('data-wallpaper', 'on')
  root.style.setProperty('--wallpaper-image', `url("${wp.image}")`)

  const fx = clamp01(wp.focusX ?? 0.5) * 100
  const fy = clamp01(wp.focusY ?? 0.5) * 100
  root.style.setProperty('--wallpaper-position', `${fx}% ${fy}%`)

  // Default scrim: darker in dark mode, lighter in light mode.
  const opacity = clamp01(wp.overlayOpacity ?? (resolved === 'dark' ? 0.4 : 0.5))
  const scrim = resolved === 'dark' ? '0, 0, 0' : '255, 255, 255'
  root.style.setProperty('--wallpaper-overlay', `rgba(${scrim}, ${opacity})`)

  if (wp.glass) {
    // Frosted glass: surfaces become translucent (so the wallpaper shows
    // through) + blurred. We derive the tint from the theme's own surface
    // color so it stays on-palette, then drive alpha via --surface-alpha.
    const themeSurface =
      (resolved === 'dark' ? getThemeSurface('dark') : getThemeSurface('light')) ??
      (resolved === 'dark' ? '#141416' : '#ffffff')
    const rgb = hexToRgb(themeSurface) ?? (resolved === 'dark' ? [20, 20, 22] : [255, 255, 255])
    const alpha = resolved === 'dark' ? 0.55 : 0.62
    root.style.setProperty('--glass-fill', `rgba(${rgb[0]}, ${rgb[1]}, ${rgb[2]}, ${alpha})`)
    root.style.setProperty('--glass-blur', '20px')
    // Also make the generic surface tokens translucent so existing cards
    // (bg-surface) read as glass without touching component code.
    root.style.setProperty('--surface-alpha', String(alpha))
  }
}

// Cache of the active theme's surface color for glass tinting.
let activeSurface: { light?: string; dark?: string } = {}
function getThemeSurface(mode: 'light' | 'dark'): string | undefined {
  return activeSurface[mode]
}

function clamp01(n: number): number {
  return Math.min(1, Math.max(0, n))
}

// Apply the persisted appearance + theme once, before React renders, so the
// first paint already has the right colors (no flash of the default theme).
export function initThemeEarly() {
  const pref = readStoredPref()
  const resolved: ResolvedTheme = pref === 'system' ? getSystemTheme() : pref
  applyAppearanceAndTheme(resolved, readStoredThemeId())
}

export function useTheme() {
  const [pref, setPref] = useState<ThemePref>(readStoredPref)
  const [themeId, setThemeIdState] = useState<string>(readStoredThemeId)
  const [themes, setThemes] = useState<Theme[]>(getAllThemes)
  const [resolved, setResolved] = useState<ResolvedTheme>(() =>
    readStoredPref() === 'system' ? getSystemTheme() : (readStoredPref() as ResolvedTheme)
  )
  // Display name; a bundled app config may override the default.
  const [appName, setAppName] = useState<string>('CowAgent')
  // Snapshot before any effect persists a value, so we can tell a genuine
  // first run (no prior choice) from a user who explicitly picked a theme.
  const [firstRun] = useState(() => !hasStoredThemeId())

  // Load themes (bundled + user) and the optional app config once on mount.
  // On a genuine first run, apply the config's default theme if one is set;
  // otherwise just re-apply the current selection now its definition is loaded.
  useEffect(() => {
    let cancelled = false
    Promise.all([
      window.electronAPI?.listThemes?.() ?? Promise.resolve([]),
      window.electronAPI?.getAppConfig?.() ?? Promise.resolve(null),
    ])
      .then(([remote, config]) => {
        if (cancelled) return
        registerRuntimeThemes(remote)
        setThemes(getAllThemes())
        if (config?.appName) setAppName(config.appName)

        // First-run default from the app config (if the theme exists).
        if (firstRun && config?.defaultTheme && getTheme(config.defaultTheme).id === config.defaultTheme) {
          setThemeIdState(config.defaultTheme) // triggers the apply effect below
          return
        }
        // Re-apply the current selection now that its definition is loaded.
        const next: ResolvedTheme = readStoredPref() === 'system' ? getSystemTheme() : (readStoredPref() as ResolvedTheme)
        applyAppearanceAndTheme(next, readStoredThemeId())
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [firstRun])

  // Re-apply whenever the appearance preference or theme changes.
  useEffect(() => {
    const next: ResolvedTheme = pref === 'system' ? getSystemTheme() : pref
    setResolved(next)
    applyAppearanceAndTheme(next, themeId)
    localStorage.setItem(PREF_KEY, pref)
    localStorage.setItem(THEME_ID_KEY, themeId)
  }, [pref, themeId])

  // Follow system changes only when preference is "system".
  useEffect(() => {
    if (pref !== 'system') return
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = () => {
      const next = getSystemTheme()
      setResolved(next)
      applyAppearanceAndTheme(next, themeId)
    }
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [pref, themeId])

  const toggleTheme = useCallback(() => {
    setPref(resolved === 'dark' ? 'light' : 'dark')
  }, [resolved])

  const setTheme = useCallback((next: ThemePref) => setPref(next), [])
  const setThemeId = useCallback((next: string) => setThemeIdState(next), [])

  return { theme: resolved, pref, themeId, themes, appName, toggleTheme, setTheme, setThemeId }
}
