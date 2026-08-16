import { create } from 'zustand'
import type { UpdateStatus } from '../types'
import { getLang } from '../i18n'

interface UpdateState {
  status: UpdateStatus | null
  /** Latest available version, kept across download progress updates. */
  version: string | null
  /** Download progress 0-100 while state === 'downloading'. */
  percent: number
  /** User clicked "download" but no progress event has arrived yet. Gives the
   *  button an instant busy state so it can't be clicked again during the 1-2s
   *  lead-up to the first progress event. Cleared on the first 'downloading'. */
  preparing: boolean
  /** The download progress already reached ~100% once. macOS (Squirrel.Mac)
   *  emits a SECOND progress pass (verify / block-map) after the first, which
   *  used to make the bar visibly restart from 0. Once peaked we render an
   *  indeterminate "verifying" state instead of a confusing second bar. */
  progressPeaked: boolean
  /** User clicked "restart to install"; show a full-screen "installing…"
   *  overlay for the brief window before the app quits to swap the bundle. */
  installing: boolean
  /** User dismissed the badge for this version (don't nag again until next). */
  dismissedVersion: string | null
  /** Whether the update panel is currently shown. Lifted here so the "check
   *  for update" menu item can re-open it on demand. */
  panelOpen: boolean

  setStatus: (s: UpdateStatus) => void
  /** Dismiss the floating badge/panel for the current version (footer dot goes
   *  away), but keep the update itself known so the menu can still surface it. */
  dismiss: () => void
  openPanel: () => void
  closePanel: () => void
  /** User explicitly clicked "check for update": ask main to re-check, and if
   *  an update is already known, re-open the panel immediately (undismiss). */
  recheck: () => void

  // Actions proxied to the main process via the preload bridge.
  download: () => void
  install: () => void
}

export const useUpdateStore = create<UpdateState>((set, get) => ({
  status: null,
  version: null,
  percent: 0,
  preparing: false,
  progressPeaked: false,
  installing: false,
  dismissedVersion: null,
  panelOpen: false,

  setStatus: (s) =>
    set((st) => {
      if (s.state === 'available') {
        // Auto-open the panel once per version, but don't nag: an automatic
        // check (startup / 4h poll) that finds a version the user already
        // dismissed leaves the panel closed and only keeps the dot lit. A
        // different (newer) version, or an explicit "check for update" click
        // (userInitiated), re-opens it. recheck() clears dismissedVersion, so a
        // manual check always satisfies the "not dismissed" condition too.
        const alreadyDismissed = st.dismissedVersion === s.version
        const shouldOpen = s.userInitiated === true || !alreadyDismissed
        return {
          status: s,
          version: s.version,
          percent: 0,
          preparing: false,
          progressPeaked: false,
          panelOpen: shouldOpen,
        }
      }
      if (s.state === 'downloading') {
        // First real progress event clears the "preparing" busy state. Track
        // when we've hit ~100% so the Squirrel.Mac second pass renders as an
        // indeterminate "verifying" state instead of a bar restarting from 0.
        const peaked = st.progressPeaked || s.percent >= 99
        return { status: s, percent: s.percent, preparing: false, progressPeaked: peaked }
      }
      if (s.state === 'downloaded')
        return { status: s, version: s.version, percent: 100, preparing: false }
      if (s.state === 'error') return { status: s, preparing: false, installing: false }
      return { status: s }
    }),

  dismiss: () => set((st) => ({ dismissedVersion: st.version, panelOpen: false })),
  openPanel: () => set({ panelOpen: true }),
  closePanel: () => set({ panelOpen: false }),

  recheck: () => {
    // Clear any dismiss so a known update surfaces again. Only re-open the panel
    // when an update actually exists — if we're already up to date, opening the
    // panel would just flash it (the banner renders nothing for not-available)
    // and the "up to date" feedback belongs in the menu, not a panel. The menu
    // (NavRail) decides whether to close itself + show the panel based on this.
    const known = hasAvailableUpdate(get())
    set({ dismissedVersion: null, panelOpen: known })
    // Always kick a fresh check too (picks up newer versions / recovers errors).
    // Pass the UI language so downloads route to the China CDN / R2 accordingly.
    window.electronAPI?.checkForUpdate?.(getLang())
  },

  download: () => {
    // Enter a busy state immediately so the button can't be clicked twice while
    // we wait (1-2s) for the first download-progress event to arrive.
    set({ preparing: true, progressPeaked: false })
    window.electronAPI?.downloadUpdate?.(getLang())
  },
  install: () => {
    // Show the "installing…" overlay before the app quits to swap the bundle.
    set({ installing: true })
    window.electronAPI?.installUpdate?.()
  },
}))

// Subscribe to main-process update events. Returns an unsubscribe fn.
export function initUpdateListener(): (() => void) | undefined {
  return window.electronAPI?.onUpdateStatus?.((status) => {
    useUpdateStore.getState().setStatus(status as UpdateStatus)
  })
}

// Whether an update exists at all (available/downloading/downloaded),
// regardless of dismiss. Drives the "check for update" menu item's dot, which
// should persist as long as an update is actually available.
export function hasAvailableUpdate(state: UpdateState): boolean {
  const s = state.status
  if (!s) return false
  return s.state === 'available' || s.state === 'downloading' || s.state === 'downloaded'
}

// Whether a new version should be surfaced in the floating footer badge:
// available and not dismissed for that version. Dismissing hides only this,
// not the menu dot (hasAvailableUpdate).
export function hasPendingUpdate(state: UpdateState): boolean {
  return hasAvailableUpdate(state) && state.dismissedVersion !== state.version
}
