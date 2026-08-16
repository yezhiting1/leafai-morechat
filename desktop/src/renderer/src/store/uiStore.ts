import { create } from 'zustand'

const NAV_KEY = 'cow_nav_collapsed'
const SESSIONS_KEY = 'cow_sessions_collapsed'

interface UIState {
  /** Navigation rail collapsed (icon-only) vs expanded (icon + label). */
  navCollapsed: boolean
  toggleNav: () => void
  setNavCollapsed: (v: boolean) => void

  /** Session list panel collapsed (hidden) vs expanded. */
  sessionsCollapsed: boolean
  toggleSessions: () => void
  setSessionsCollapsed: (v: boolean) => void

  /** Currently active session id (Chat page). */
  activeSessionId: string | null
  setActiveSessionId: (id: string | null) => void
}

function readBool(key: string): boolean {
  return localStorage.getItem(key) === '1'
}

export const useUIStore = create<UIState>((set) => ({
  navCollapsed: readBool(NAV_KEY),
  toggleNav: () =>
    set((s) => {
      const next = !s.navCollapsed
      localStorage.setItem(NAV_KEY, next ? '1' : '0')
      return { navCollapsed: next }
    }),
  setNavCollapsed: (v) => {
    localStorage.setItem(NAV_KEY, v ? '1' : '0')
    set({ navCollapsed: v })
  },

  sessionsCollapsed: readBool(SESSIONS_KEY),
  toggleSessions: () =>
    set((s) => {
      const next = !s.sessionsCollapsed
      localStorage.setItem(SESSIONS_KEY, next ? '1' : '0')
      return { sessionsCollapsed: next }
    }),
  setSessionsCollapsed: (v) => {
    localStorage.setItem(SESSIONS_KEY, v ? '1' : '0')
    set({ sessionsCollapsed: v })
  },

  activeSessionId: null,
  setActiveSessionId: (id) => set({ activeSessionId: id }),
}))
