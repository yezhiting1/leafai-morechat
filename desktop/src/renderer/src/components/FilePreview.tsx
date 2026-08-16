import React, { useEffect, useState } from 'react'
import { Eye, AlertTriangle, Loader2, Download } from 'lucide-react'
import hljs from 'highlight.js'
import { t } from '../i18n'
import apiClient from '../api/client'
import Markdown from './Markdown'
import { iconFor, colorFor } from '../lib/fileKind'
import type { WorkspaceEntry } from '../types'

interface FilePreviewProps {
  file: WorkspaceEntry | null
  error?: string | null
}

const Centered: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div className="h-full flex flex-col items-center justify-center gap-2.5 px-6 text-center text-content-tertiary text-[13px]">
    {children}
  </div>
)

/** Text-based previews (markdown / code / csv) fetch the file, then render. */
const TextPreview: React.FC<{ file: WorkspaceEntry }> = ({ file }) => {
  const [state, setState] = useState<{ text?: string; error?: string; loading: boolean }>({
    loading: true,
  })

  useEffect(() => {
    let cancelled = false
    setState({ loading: true })
    fetch(apiClient.getPreviewUrl(file.preview_url!))
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.text()
      })
      .then((text) => !cancelled && setState({ text, loading: false }))
      .catch((e) => !cancelled && setState({ error: String(e.message || e), loading: false }))
    return () => {
      cancelled = true
    }
  }, [file.preview_url])

  if (state.loading) {
    return (
      <Centered>
        <Loader2 size={20} className="animate-spin" />
      </Centered>
    )
  }
  if (state.error) {
    return (
      <Centered>
        <AlertTriangle size={22} className="opacity-50" />
        <span>
          {t('ws_preview_failed')}: {state.error}
        </span>
      </Centered>
    )
  }
  if (file.kind === 'markdown') {
    return (
      <div className="p-4">
        <Markdown content={state.text || ''} />
      </div>
    )
  }

  const lang = file.name.split('.').pop()?.toLowerCase() || ''
  const highlighted =
    file.kind === 'code' && hljs.getLanguage(lang)
      ? hljs.highlight(state.text || '', { language: lang }).value
      : null

  return (
    <pre className="m-0 p-4 text-[12.5px] leading-relaxed overflow-auto">
      {highlighted ? (
        <code className="hljs" dangerouslySetInnerHTML={{ __html: highlighted }} />
      ) : (
        <code>{state.text}</code>
      )}
    </pre>
  )
}

const FilePreview: React.FC<FilePreviewProps> = ({ file, error }) => {
  if (error) {
    return (
      <Centered>
        <AlertTriangle size={24} className="opacity-50" />
        <span>
          {t('ws_preview_failed')}: {error}
        </span>
      </Centered>
    )
  }

  if (!file) {
    return (
      <Centered>
        <Eye size={24} className="opacity-40" />
        <span>{t('ws_preview_empty')}</span>
      </Centered>
    )
  }

  const src = file.preview_url ? apiClient.getPreviewUrl(file.preview_url) : ''
  const rawSrc = apiClient.getFileUrl(file.raw_url || file.preview_url || '')

  switch (file.kind) {
    case 'html':
      return (
        <iframe
          key={src}
          src={src}
          title={file.name}
          className="w-full h-full border-0 bg-white"
          // No allow-same-origin: the generated page runs in an opaque origin
          // and can't reach the app's storage or the backend auth cookie.
          sandbox="allow-scripts allow-popups allow-forms allow-modals"
        />
      )

    case 'pdf':
      return <iframe key={src} src={src} title={file.name} className="w-full h-full border-0" />

    case 'image':
      return (
        <div className="p-4">
          <img src={rawSrc} alt={file.name} className="max-w-full mx-auto rounded-lg" />
        </div>
      )

    case 'video':
      return (
        <div className="p-4">
          <video src={rawSrc} controls preload="metadata" className="max-w-full mx-auto rounded-lg" />
        </div>
      )

    case 'audio':
      return (
        <div className="p-4">
          <audio src={rawSrc} controls className="w-full" />
        </div>
      )

    case 'markdown':
    case 'code':
    case 'text':
    case 'csv':
      return <TextPreview file={file} />

    default: {
      const Icon = iconFor(file.kind)
      return (
        <Centered>
          <Icon size={26} className={colorFor(file.kind)} />
          <span className="text-content">{file.name}</span>
          <span>{t('ws_no_inline_preview')}</span>
          <button
            onClick={() => window.open(rawSrc, '_blank')}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-btn border border-default hover:border-accent hover:text-accent cursor-pointer transition-colors"
          >
            <Download size={13} />
            {t('ws_download')}
          </button>
        </Centered>
      )
    }
  }
}

export default FilePreview
