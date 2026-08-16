import React from 'react'
import { Eye, Download } from 'lucide-react'
import { t } from '../i18n'
import apiClient from '../api/client'
import { useWorkspaceStore } from '../store/workspaceStore'
import { iconFor, colorFor, formatSize, kindOf, PREVIEWABLE_KINDS } from '../lib/fileKind'
import type { Artifact } from '../types'

/** Partial artifact: history-rebuilt cards only know the path. */
export type FileCardMeta = Pick<Artifact, 'file_name' | 'rel_path'> & Partial<Artifact>

interface FileCardProps {
  meta: FileCardMeta
}

const FileCard: React.FC<FileCardProps> = ({ meta }) => {
  const preview = useWorkspaceStore((s) => s.preview)
  const kind = meta.kind || kindOf(meta.file_name)
  const Icon = iconFor(kind)
  const canPreview = meta.previewable ?? PREVIEWABLE_KINDS.has(kind)
  // Only show the path when it says more than the file name already does.
  const sub = [meta.rel_path === meta.file_name ? '' : meta.rel_path, formatSize(meta.size)]
    .filter(Boolean)
    .join(' · ')

  const open = () => preview(meta.preview_url ? (meta as Artifact) : meta.abs_path || meta.rel_path)

  const download = async (e: React.MouseEvent) => {
    e.stopPropagation()
    let url = meta.raw_url
    if (!url) {
      try {
        url = (await apiClient.workspaceResolve(meta.abs_path || meta.rel_path)).file.raw_url
      } catch {
        return
      }
    }
    window.open(apiClient.getFileUrl(url!), '_blank')
  }

  return (
    <div
      onClick={open}
      className="group/card inline-flex items-center gap-2.5 max-w-full mt-2 px-3 py-2 rounded-xl border border-default bg-surface-2 cursor-pointer hover:border-accent transition-colors"
    >
      <Icon size={16} className={`shrink-0 ${colorFor(kind)}`} />
      <div className="min-w-0 flex-1">
        <div className="text-[13px] font-medium text-content truncate">{meta.file_name}</div>
        {sub && <div className="text-[11px] text-content-tertiary truncate">{sub}</div>}
      </div>
      <div className="flex items-center gap-0.5 shrink-0">
        {canPreview && (
          <span
            title={t('ws_preview')}
            className="w-6 h-6 flex items-center justify-center rounded-md text-content-tertiary hover:text-content hover:bg-surface transition-colors"
          >
            <Eye size={12} />
          </span>
        )}
        <span
          onClick={download}
          title={t('ws_download')}
          className="w-6 h-6 flex items-center justify-center rounded-md text-content-tertiary hover:text-content hover:bg-surface transition-colors"
        >
          <Download size={12} />
        </span>
      </div>
    </div>
  )
}

export default FileCard
