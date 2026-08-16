import React, { useCallback, useEffect, useRef, useState } from 'react'
import { Eye, FolderTree, ExternalLink, Download, Link2, Check, X } from 'lucide-react'
import { t } from '../i18n'
import apiClient from '../api/client'
import FilePreview from './FilePreview'
import FileTree from './FileTree'
import { useWorkspaceStore, WS_MIN_WIDTH } from '../store/workspaceStore'

const TabButton: React.FC<{
  active: boolean
  onClick: () => void
  icon: React.ReactNode
  label: string
}> = ({ active, onClick, icon, label }) => (
  <button
    onClick={onClick}
    className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-btn text-[13px] font-medium cursor-pointer transition-colors ${
      active ? 'bg-accent-soft text-accent' : 'text-content-tertiary hover:text-content hover:bg-surface-2'
    }`}
  >
    {icon}
    {label}
  </button>
)

const IconButton: React.FC<{ onClick: () => void; title: string; children: React.ReactNode }> = ({
  onClick,
  title,
  children,
}) => (
  <button
    onClick={onClick}
    title={title}
    className="w-7 h-7 flex items-center justify-center rounded-btn text-content-tertiary hover:text-content hover:bg-surface-2 cursor-pointer transition-colors"
  >
    {children}
  </button>
)

const WorkspacePanel: React.FC = () => {
  const { open, tab, width, current, previewError } = useWorkspaceStore()
  const setTab = useWorkspaceStore((s) => s.setTab)
  const setWidth = useWorkspaceStore((s) => s.setWidth)
  const closePanel = useWorkspaceStore((s) => s.closePanel)
  const [copied, setCopied] = useState(false)
  // Dragging the divider over the preview iframe would otherwise lose the
  // mousemove stream to the iframe's document.
  const [resizing, setResizing] = useState(false)
  const widthRef = useRef(width)
  widthRef.current = width

  const startResize = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault()
      const startX = e.clientX
      const startWidth = widthRef.current
      setResizing(true)
      const onMove = (ev: MouseEvent) => {
        setWidth(Math.min(window.innerWidth * 0.7, Math.max(WS_MIN_WIDTH, startWidth + startX - ev.clientX)))
      }
      const onUp = () => {
        setResizing(false)
        document.removeEventListener('mousemove', onMove)
        document.removeEventListener('mouseup', onUp)
      }
      document.addEventListener('mousemove', onMove)
      document.addEventListener('mouseup', onUp)
    },
    [setWidth]
  )

  useEffect(() => {
    setCopied(false)
  }, [current?.path])

  if (!open) return null

  const showFileActions = tab === 'preview' && !!current

  const openExternally = () => {
    if (!current) return
    // Desktop can hand the file to the OS default app; fall back to the browser.
    if (current.abs_path && window.electronAPI?.openPath) {
      window.electronAPI.openPath(current.abs_path)
      return
    }
    window.open(apiClient.getPreviewUrl(current.preview_url || ''), '_blank')
  }

  const download = () => {
    if (!current) return
    window.open(apiClient.getFileUrl(current.raw_url || current.preview_url || ''), '_blank')
  }

  const copyPath = () => {
    if (!current) return
    navigator.clipboard.writeText(current.abs_path || current.path)
    setCopied(true)
    setTimeout(() => setCopied(false), 1600)
  }

  return (
    <aside
      // Cap against the viewport so a width remembered on a large window
      // can't crowd out the chat on a smaller one.
      style={{ width, maxWidth: '70vw' }}
      className="relative shrink-0 h-full flex border-l border-default bg-base"
    >
      <div
        onMouseDown={startResize}
        className="absolute -left-[3px] top-0 bottom-0 w-1.5 cursor-col-resize z-20 hover:bg-accent/30"
      />

      <div className="flex-1 min-w-0 flex flex-col">
        <div className="h-[44px] shrink-0 flex items-center justify-between gap-2 pl-2.5 pr-1.5 border-b border-default">
          <div className="flex items-center gap-0.5">
            <TabButton
              active={tab === 'preview'}
              onClick={() => setTab('preview')}
              icon={<Eye size={13} />}
              label={t('ws_tab_preview')}
            />
            <TabButton
              active={tab === 'files'}
              onClick={() => setTab('files')}
              icon={<FolderTree size={13} />}
              label={t('ws_tab_files')}
            />
          </div>
          <div className="flex items-center gap-0.5">
            {showFileActions && (
              <>
                <IconButton onClick={openExternally} title={t('ws_open_external')}>
                  <ExternalLink size={13} />
                </IconButton>
                <IconButton onClick={download} title={t('ws_download')}>
                  <Download size={13} />
                </IconButton>
                <IconButton onClick={copyPath} title={t('ws_copy_path')}>
                  {copied ? <Check size={13} /> : <Link2 size={13} />}
                </IconButton>
              </>
            )}
            <IconButton onClick={() => closePanel(true)} title={t('ws_close')}>
              <X size={14} />
            </IconButton>
          </div>
        </div>

        {/* Both tabs stay mounted so the file tree keeps its scroll position
            and loaded directory when the user flips to a preview and back. */}
        <div className={`flex-1 min-h-0 flex-col ${tab === 'preview' ? 'flex' : 'hidden'}`}>
          {current && (
            <div className="shrink-0 px-3 py-2 text-[11px] font-mono text-content-tertiary border-b border-default break-all">
              {current.path}
            </div>
          )}
          <div
            className="flex-1 min-h-0 overflow-auto"
            style={resizing ? { pointerEvents: 'none' } : undefined}
          >
            <FilePreview file={current} error={previewError} />
          </div>
        </div>

        <div className={`flex-1 min-h-0 flex-col ${tab === 'files' ? 'flex' : 'hidden'}`}>
          <FileTree />
        </div>
      </div>
    </aside>
  )
}

export default WorkspacePanel
