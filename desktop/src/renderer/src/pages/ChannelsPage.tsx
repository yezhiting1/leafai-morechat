import React, { useEffect, useMemo, useRef, useState } from 'react'
import {
  Loader2,
  Plug,
  Plus,
  X,
  ChevronDown,
  Check,
  MessageCircle,
  MessageSquare,
  Bot,
  Building2,
  Headset,
  Hash,
  AtSign,
  RadioTower,
  QrCode,
  KeyRound,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { t, localizedLabel, getLang } from '../i18n'
import apiClient from '../api/client'
import type { ChannelInfo, ChannelField } from '../types'
import { Toggle, Btn } from './settings/primitives'
import QrScanPanel from '../components/QrScanPanel'
import { PaperPlaneIcon } from '../components/icons'

// Channels that connect via QR scanning rather than credential fields.
const QR_PROVIDERS: Record<string, 'weixin' | 'feishu'> = { weixin: 'weixin', feishu: 'feishu' }

// A running WeChat channel reports its own login state, which does not always
// match "connected": it can still be booting, or be waiting for someone to
// scan its QR. Anything else (including every other channel) has nothing
// pending and is simply shown as connected.
type Pending = 'none' | 'scanning' | 'starting'

const pendingState = (ch: ChannelInfo): Pending => {
  const s = ch.login_status
  if (ch.name !== 'weixin' || !ch.active || !s || s === 'logged_in') return 'none'
  // 'idle'/'unknown' mean the channel is still coming up (the connect handler
  // waits a few seconds before starting it) — not something to scan for.
  return s === 'waiting_scan' || s === 'scanned' ? 'scanning' : 'starting'
}

// An icon component that takes a `size` prop (lucide icons and our PaperPlaneIcon).
type IconComponent = React.FC<{ size?: number }>

// Per-channel icon + accent color, mirroring the web console's FontAwesome
// icon + Tailwind color palette (we use lucide here, with hex colors so the
// tinted icon background isn't purged by Tailwind's JIT). Feishu/Telegram use
// the same paper-plane as the web console.
const CHANNEL_STYLE: Record<string, { Icon: IconComponent; color: string }> = {
  weixin: { Icon: MessageCircle, color: '#10b981' },
  feishu: { Icon: PaperPlaneIcon, color: '#3b82f6' },
  dingtalk: { Icon: MessageSquare, color: '#3b82f6' },
  wecom_bot: { Icon: Bot, color: '#10b981' },
  qq: { Icon: MessageCircle, color: '#3b82f6' },
  wechatcom_app: { Icon: Building2, color: '#10b981' },
  wechat_kf: { Icon: Headset, color: '#10b981' },
  wechatmp: { Icon: MessageCircle, color: '#10b981' },
  telegram: { Icon: PaperPlaneIcon, color: '#0ea5e9' },
  slack: { Icon: Hash, color: '#a855f7' },
  discord: { Icon: AtSign, color: '#6366f1' },
}

const channelStyle = (name: string) => CHANNEL_STYLE[name] ?? { Icon: Plug, color: '#94a3b8' }

interface ChannelsPageProps {
  baseUrl: string
}

// A masked secret looks like "abcd****wxyz"; the backend skips such values.
const MASK_RE = /\*{2,}/

const ChannelsPage: React.FC<ChannelsPageProps> = ({ baseUrl }) => {
  const [channels, setChannels] = useState<ChannelInfo[]>([])
  const [loading, setLoading] = useState(true)
  // Whether the "add channel" panel is open, and the channel chosen in it.
  // `selected` starts empty so the user must pick a channel themselves.
  const [addOpen, setAddOpen] = useState(false)
  const [selected, setSelected] = useState<string>('')
  const scrollRef = useRef<HTMLDivElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)

  // `silent` refreshes keep the current list on screen (used by the WeChat
  // login watcher, which must not flash the spinner every few seconds).
  const loadChannels = async (silent = false) => {
    try {
      if (!silent) setLoading(true)
      const data = await apiClient.getChannels()
      setChannels(data || [])
    } catch (err) {
      console.error('Failed to load channels:', err)
      if (!silent) setChannels([])
    } finally {
      if (!silent) setLoading(false)
    }
  }

  // Refetch on a language switch too: the backend orders the list for the
  // language we ask with, so the old response is stale once that changes.
  useEffect(() => {
    apiClient.setBaseUrl(baseUrl)
    void loadChannels()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [baseUrl, getLang()])

  // While a channel is still settling (booting, or waiting for a scan that may
  // happen elsewhere), poll so its card flips to "connected" on its own.
  const settling = channels.some((c) => pendingState(c) !== 'none')
  useEffect(() => {
    if (!settling) return
    const id = setInterval(() => void loadChannels(true), 3000)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settling])

  const { connected, available } = useMemo(() => {
    const connected = channels.filter((c) => c.active)
    const available = channels.filter((c) => !c.active)
    return { connected, available }
  }, [channels])

  // If the selected channel got connected (or vanished), clear the selection.
  useEffect(() => {
    if (selected && !available.some((c) => c.name === selected)) setSelected('')
  }, [available, selected])

  const openAdd = () => {
    setSelected('')
    setAddOpen(true)
    // Scroll the new panel into view at the bottom of the list.
    requestAnimationFrame(() => {
      panelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
    })
  }

  const addingChannel = available.find((c) => c.name === selected)

  const onAdded = () => {
    setAddOpen(false)
    setSelected('')
    void loadChannels()
  }

  // Keep the config form in view as it grows after picking a channel.
  useEffect(() => {
    if (selected) {
      requestAnimationFrame(() => {
        panelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
      })
    }
  }, [selected])

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div className="px-6 pt-5 pb-3 flex-shrink-0 flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-content">{t('channels_title')}</h2>
          <p className="text-xs text-content-tertiary mt-1">{t('channels_desc')}</p>
        </div>
        {!loading && available.length > 0 && !addOpen && (
          <Btn variant="primary" onClick={openAdd}>
            <span className="flex items-center gap-1.5">
              <Plus size={15} />
              {t('channels_add')}
            </span>
          </Btn>
        )}
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto border-t border-default">
        <div className="max-w-3xl mx-auto px-6 py-5">
          {loading ? (
            <div className="flex items-center justify-center py-20 text-content-tertiary">
              <Loader2 size={18} className="animate-spin mr-2" />
              {t('channels_loading')}
            </div>
          ) : (
            <div className="space-y-3">
              {connected.length === 0 && !addOpen ? (
                <div className="flex flex-col items-center justify-center text-center py-16 px-6">
                  <span className="w-16 h-16 rounded-2xl bg-info/10 flex items-center justify-center mb-4">
                    <RadioTower size={26} className="text-info" />
                  </span>
                  <p className="text-content-secondary font-medium">{t('channels_empty')}</p>
                  <p className="text-sm text-content-tertiary mt-1.5 max-w-sm leading-relaxed">
                    {t('channels_empty_desc')}
                  </p>
                  {available.length > 0 && (
                    <div className="mt-5">
                      <Btn variant="primary" onClick={openAdd}>
                        <span className="flex items-center gap-1.5">
                          <Plus size={15} />
                          {t('channels_add')}
                        </span>
                      </Btn>
                    </div>
                  )}
                </div>
              ) : (
                connected.map((ch) => <ChannelCard key={ch.name} channel={ch} onChanged={loadChannels} />)
              )}

              {/* Add-channel panel lives at the bottom of the list: pick a
                  channel from the dropdown, then configure/connect it inline. */}
              {addOpen && available.length > 0 && (
                <div ref={panelRef} className="rounded-card border border-accent/40 bg-surface p-4 space-y-4">
                  <div className="flex items-center justify-between gap-3">
                    <label className="text-sm font-medium text-content">{t('channels_select_label')}</label>
                    <button
                      onClick={() => setAddOpen(false)}
                      className="text-content-tertiary hover:text-content cursor-pointer"
                      title={t('channels_add_close')}
                    >
                      <X size={16} />
                    </button>
                  </div>
                  <ChannelDropdown
                    channels={available}
                    value={selected}
                    onChange={setSelected}
                    placeholder={t('channels_select_placeholder')}
                  />
                  {addingChannel && (
                    <ChannelCard key={addingChannel.name} channel={addingChannel} onChanged={onAdded} defaultExpanded />
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// Custom dropdown styled like the web console's `.cfg-dropdown` (rounded,
// green focus ring, hover/active states) instead of a native <select>.
const ChannelDropdown: React.FC<{
  channels: ChannelInfo[]
  value: string
  onChange: (name: string) => void
  placeholder: string
}> = ({ channels, value, onChange, placeholder }) => {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open])

  const current = channels.find((c) => c.name === value)

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={`w-full flex items-center justify-between gap-2 h-10 px-3 rounded-btn border bg-inset text-sm cursor-pointer transition-colors ${
          open ? 'border-accent ring-2 ring-accent/15' : 'border-strong hover:border-content-tertiary'
        } ${current ? 'text-content' : 'text-content-tertiary'}`}
      >
        {current ? (
          <span className="flex items-center gap-2 min-w-0">
            <ChannelIcon name={current.name} size={26} />
            <span className="truncate">{localizedLabel(current.label)}</span>
            <span className="text-content-tertiary font-mono text-xs">({current.name})</span>
          </span>
        ) : (
          <span>{placeholder}</span>
        )}
        <ChevronDown size={14} className={`flex-shrink-0 text-content-tertiary transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="absolute top-[calc(100%+4px)] left-0 right-0 z-50 max-h-60 overflow-y-auto rounded-btn border border-default bg-elevated shadow-lg p-1">
          {channels.map((ch) => {
            const active = ch.name === value
            return (
              <button
                key={ch.name}
                type="button"
                onClick={() => {
                  onChange(ch.name)
                  setOpen(false)
                }}
                className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-md text-sm cursor-pointer transition-colors ${
                  active ? 'bg-accent-soft text-accent font-medium' : 'text-content-secondary hover:bg-surface-2'
                }`}
              >
                <ChannelIcon name={ch.name} size={26} />
                <span className="truncate">{localizedLabel(ch.label)}</span>
                <span className="text-content-tertiary font-mono text-xs">({ch.name})</span>
                {active && <Check size={14} className="ml-auto flex-shrink-0" />}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

// A tinted square with the channel's icon (web-console style).
const ChannelIcon: React.FC<{ name: string; size?: number }> = ({ name, size = 36 }) => {
  const { Icon, color } = channelStyle(name)
  return (
    <span
      className="rounded-lg flex items-center justify-center flex-shrink-0"
      style={{ width: size, height: size, backgroundColor: `${color}1a`, color }}
    >
      <Icon size={Math.round(size * 0.45)} />
    </span>
  )
}

// Segmented tab used by channels that support several connect modes.
const ModeTab: React.FC<{ icon: LucideIcon; label: string; active: boolean; onClick: () => void }> = ({
  icon: Icon,
  label,
  active,
  onClick,
}) => (
  <button
    type="button"
    onClick={onClick}
    className={`flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-[6px] text-sm font-medium cursor-pointer transition-colors ${
      active ? 'bg-surface text-content shadow-sm' : 'text-content-tertiary hover:text-content-secondary'
    }`}
  >
    <Icon size={14} />
    {label}
  </button>
)

const ChannelCard: React.FC<{ channel: ChannelInfo; onChanged: () => void; defaultExpanded?: boolean }> = ({
  channel,
  onChanged,
  defaultExpanded = false,
}) => {
  // Channels with no fields connect purely via QR (e.g. weixin).
  const isQrLogin = channel.fields.length === 0
  // QR provider supported by the desktop scan panel (weixin / feishu).
  const qrProvider = QR_PROVIDERS[channel.name]
  // Feishu can be connected either by scanning a QR (which creates the app for
  // the user) or by pasting credentials, so it gets a tab switcher.
  const dualMode = !!qrProvider && !isQrLogin
  const pending = pendingState(channel)
  // WeChat goes straight to the QR: when it is being added, and when a running
  // channel lost its login. No intermediate button to click (or double-click).
  const weixinQr = qrProvider === 'weixin' && (pending === 'scanning' || (!channel.active && defaultExpanded))
  // Feishu's scan creates a brand new app, so it stays behind a button.
  const [feishuScanning, setFeishuScanning] = useState(false)
  // Stored credentials mean the user most likely wants to edit them.
  const [mode, setMode] = useState<'scan' | 'manual'>(() =>
    channel.fields.some((f) => f.type !== 'bool' && !!f.value) ? 'manual' : 'scan'
  )
  const [expanded, setExpanded] = useState(defaultExpanded)
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(channel.fields.map((f) => [f.key, f.value != null ? String(f.value) : '']))
  )
  // Track which secret fields still hold the server-provided mask.
  const [masked, setMasked] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(
      channel.fields.map((f) => [f.key, f.type === 'secret' && !!f.value && MASK_RE.test(String(f.value))])
    )
  )
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState('')

  const setField = (key: string, val: string) => setValues((p) => ({ ...p, [key]: val }))

  // Only send fields the user actually changed; masked secrets are skipped so
  // the backend keeps the stored value (mirrors the web console behavior).
  const buildConfig = (): Record<string, unknown> => {
    const cfg: Record<string, unknown> = {}
    channel.fields.forEach((f) => {
      const v = values[f.key]
      if (f.type === 'secret' && masked[f.key]) return
      if (v === '' || v == null) return
      cfg[f.key] = f.type === 'number' ? Number(v) : v
    })
    return cfg
  }

  const run = async (action: 'save' | 'connect' | 'disconnect') => {
    setBusy(true)
    setStatus('')
    try {
      const cfg = action === 'disconnect' ? undefined : buildConfig()
      const res = await apiClient.channelAction(action, channel.name, cfg)
      if (res.status === 'success') {
        if (action === 'save') {
          setStatus(t('channels_save_ok'))
          setTimeout(() => setStatus(''), 1600)
        } else if (action === 'connect' && res.downloading) {
          // Feishu fetches its SDK bundle in the background on first enable.
          setStatus(t('feishu_sdk_downloading_hint'))
          setTimeout(() => setStatus(''), 8000)
        }
        onChanged()
      } else {
        setStatus((res.message as string) || t(action === 'connect' ? 'channels_connect_error' : 'channels_save_error'))
      }
    } catch {
      setStatus(t(action === 'connect' ? 'channels_connect_error' : 'channels_save_error'))
    } finally {
      setBusy(false)
    }
  }

  const fieldEditor = (
    <div className="space-y-3">
      {channel.fields.map((f) => (
        <FieldRow
          key={f.key}
          field={f}
          value={values[f.key] ?? ''}
          onChange={(v) => setField(f.key, v)}
          onFocusSecret={() => {
            if (f.type === 'secret' && masked[f.key]) {
              setField(f.key, '')
              setMasked((p) => ({ ...p, [f.key]: false }))
            }
          }}
        />
      ))}
      <div className="flex items-center justify-end gap-3 pt-1">
        <span className={`text-xs transition-opacity ${status ? 'opacity-100' : 'opacity-0'} ${status === t('channels_save_ok') ? 'text-accent' : 'text-danger'}`}>
          {status || '\u00a0'}
        </span>
        {channel.active ? (
          <Btn variant="primary" onClick={() => run('save')} disabled={busy}>
            {t('channels_save')}
          </Btn>
        ) : (
          <Btn variant="primary" onClick={() => run('connect')} disabled={busy}>
            {t('channels_connect')}
          </Btn>
        )}
      </div>
    </div>
  )

  return (
    <div className={defaultExpanded ? '' : 'rounded-card border border-default bg-surface p-4'}>
      <div className="flex items-center gap-3">
        <ChannelIcon name={channel.name} size={40} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium text-sm text-content">{localizedLabel(channel.label)}</span>
            <span
              className={`w-2 h-2 rounded-full ${
                pending !== 'none'
                  ? 'bg-warning animate-pulse'
                  : channel.active
                    ? 'bg-accent'
                    : 'bg-content-tertiary'
              }`}
            />
            {pending === 'scanning' ? (
              <span className={`text-xs ${channel.login_status === 'scanned' ? 'text-accent' : 'text-warning'}`}>
                {channel.login_status === 'scanned' ? t('weixin_scan_scanned') : t('weixin_scan_waiting')}
              </span>
            ) : pending === 'starting' ? (
              <span className="text-xs text-warning">{t('channels_starting')}</span>
            ) : channel.active ? (
              <span className="text-xs text-accent">{t('channels_connected')}</span>
            ) : null}
          </div>
          <p className="text-xs text-content-tertiary font-mono mt-0.5">{channel.name}</p>
        </div>

        {channel.active ? (
          <Btn variant="danger" onClick={() => run('disconnect')} disabled={busy}>
            {t('channels_disconnect')}
          </Btn>
        ) : isQrLogin || dualMode || defaultExpanded ? null : (
          <Btn variant="ghost" onClick={() => setExpanded((v) => !v)}>
            {t('channels_add')}
          </Btn>
        )}
      </div>

      {/* QR-login channels with no desktop support fall back to the web console. */}
      {isQrLogin && !channel.active && !qrProvider && (
        <p className="text-xs text-content-tertiary mt-3 pl-12">{t('channels_qr_hint')}</p>
      )}

      {/* WeChat: the QR is the whole flow, so show it right away. The amber
          "waiting for scan" badge is what tells a live card why it reappeared. */}
      {weixinQr && (
        <div className={channel.active ? 'mt-4 pt-4 border-t border-subtle' : 'mt-2'}>
          <QrScanPanel provider="weixin" onConnected={onChanged} />
        </div>
      )}

      {/* Feishu: pick between one-click QR registration and manual credentials. */}
      {dualMode && (
        <div className="mt-4">
          <div className="flex items-center gap-1 bg-inset rounded-btn p-0.5 mb-4">
            <ModeTab
              icon={QrCode}
              label={t('feishu_mode_scan')}
              active={mode === 'scan'}
              onClick={() => setMode('scan')}
            />
            <ModeTab
              icon={KeyRound}
              label={t('feishu_mode_manual')}
              active={mode === 'manual'}
              onClick={() => {
                setMode('manual')
                // Drop the pending scan so coming back doesn't silently start
                // a second app registration.
                setFeishuScanning(false)
              }}
            />
          </div>
          {mode !== 'scan' ? (
            fieldEditor
          ) : feishuScanning ? (
            <QrScanPanel provider="feishu" onConnected={onChanged} />
          ) : (
            <div className="flex flex-col items-center py-3">
              <p className="text-sm text-content-secondary mb-4 text-center max-w-sm leading-relaxed">
                {channel.active ? t('feishu_scan_replace_desc') : t('feishu_scan_panel_desc')}
              </p>
              <Btn variant="primary" onClick={() => setFeishuScanning(true)}>
                <span className="flex items-center gap-1.5">
                  <QrCode size={15} />
                  {t('feishu_scan_btn')}
                </span>
              </Btn>
            </div>
          )}
        </div>
      )}

      {/* Field editor: always for connected channels with fields, on-demand for available ones. */}
      {!isQrLogin && !dualMode && (channel.active || expanded) && <div className="mt-4">{fieldEditor}</div>}
    </div>
  )
}

const FieldRow: React.FC<{
  field: ChannelField
  value: string
  onChange: (v: string) => void
  onFocusSecret: () => void
}> = ({ field, value, onChange, onFocusSecret }) => {
  if (field.type === 'bool') {
    return (
      <div className="flex items-center justify-between">
        <span className="text-sm text-content-secondary">{field.label}</span>
        <Toggle checked={value === 'true' || value === '1'} onChange={(v) => onChange(v ? 'true' : 'false')} />
      </div>
    )
  }
  return (
    <div>
      <label className="block text-sm text-content-secondary mb-1.5">{field.label}</label>
      <input
        type={field.type === 'number' ? 'number' : 'text'}
        value={value}
        placeholder={field.label}
        onChange={(e) => onChange(e.target.value)}
        onFocus={onFocusSecret}
        className="w-full px-3 py-2 rounded-btn border border-strong bg-inset text-sm text-content placeholder:text-content-tertiary focus:outline-none focus:border-accent font-mono transition-colors"
      />
    </div>
  )
}

export default ChannelsPage
