import {
  File as FileIcon,
  FileCode,
  FileText,
  FileImage,
  FileVideo,
  FileAudio,
  FileSpreadsheet,
  FileType,
  Folder,
  type LucideIcon,
} from 'lucide-react'
import type { Attachment, FileKind } from '../types'

const EXT_BY_KIND: Record<Exclude<FileKind, 'directory' | 'file'>, string[]> = {
  html: ['html', 'htm'],
  markdown: ['md', 'markdown'],
  image: ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg', 'ico'],
  video: ['mp4', 'webm', 'mov', 'avi', 'mkv', 'm4v'],
  audio: ['mp3', 'wav', 'ogg', 'm4a', 'flac', 'aac'],
  pdf: ['pdf'],
  csv: ['csv', 'tsv'],
  code: [
    'py', 'js', 'ts', 'tsx', 'jsx', 'java', 'c', 'cpp', 'h', 'go', 'rs', 'rb',
    'php', 'sh', 'sql', 'css', 'scss', 'json', 'yaml', 'yml', 'xml', 'toml', 'ini',
  ],
  office: ['doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx'],
  text: ['txt', 'log'],
}

const KIND_BY_EXT: Record<string, FileKind> = {}
for (const [kind, exts] of Object.entries(EXT_BY_KIND)) {
  for (const ext of exts) KIND_BY_EXT[ext] = kind as FileKind
}

export const PREVIEWABLE_KINDS: ReadonlySet<FileKind> = new Set<FileKind>([
  'html', 'markdown', 'image', 'video', 'audio', 'pdf', 'csv', 'code', 'text',
])

export function kindOf(name: string): FileKind {
  const ext = (name || '').split('.').pop()?.toLowerCase() || ''
  return KIND_BY_EXT[ext] || 'file'
}

/**
 * Decide whether an href points at a workspace file rather than the web.
 *
 * Agent replies cite their own files with a workspace-relative markdown link
 * (`[title](knowledge/x.md)`). Handing one to the OS browser opens a 404, so
 * they need routing to the preview panel instead.
 *
 * @returns the cleaned workspace path, or null if the href isn't one.
 */
export function workspaceHrefOf(href: string): string | null {
  if (!href) return null
  // A scheme (http, mailto, file, data), a protocol-relative host, an in-page
  // anchor or a site-absolute path is never a workspace file.
  if (/^[a-zA-Z][\w+.-]*:/.test(href)) return null
  if (href.startsWith('//') || href.startsWith('#') || href.startsWith('/')) return null

  let path = href.split('#')[0].split('?')[0].trim()
  // markdown-it percent-encodes non-ASCII hrefs; the API wants them raw.
  try {
    path = decodeURI(path)
  } catch {
    /* keep the encoded form */
  }
  if (!path) return null
  // Require a known extension so prose links stay untouched.
  return KIND_BY_EXT[(path.split('.').pop() || '').toLowerCase()] ? path : null
}

const ICON_BY_KIND: Record<FileKind, LucideIcon> = {
  directory: Folder,
  html: FileCode,
  markdown: FileText,
  image: FileImage,
  video: FileVideo,
  audio: FileAudio,
  pdf: FileType,
  csv: FileSpreadsheet,
  code: FileCode,
  office: FileText,
  text: FileText,
  file: FileIcon,
}

const COLOR_BY_KIND: Record<FileKind, string> = {
  directory: 'text-amber-500',
  html: 'text-orange-500',
  markdown: 'text-indigo-500',
  image: 'text-emerald-500',
  video: 'text-pink-500',
  audio: 'text-violet-500',
  pdf: 'text-red-500',
  csv: 'text-teal-500',
  code: 'text-blue-500',
  office: 'text-blue-600',
  text: 'text-content-tertiary',
  file: 'text-content-tertiary',
}

export function iconFor(kind: FileKind): LucideIcon {
  return ICON_BY_KIND[kind] || FileIcon
}

export function colorFor(kind: FileKind): string {
  return COLOR_BY_KIND[kind] || COLOR_BY_KIND.file
}

export function formatSize(bytes?: number): string {
  if (bytes == null) return ''
  const units = ['B', 'KB', 'MB', 'GB']
  let n = bytes
  for (const u of units) {
    if (n < 1024) return `${u === 'B' ? Math.round(n) : n.toFixed(1)}${u}`
    n /= 1024
  }
  return `${n.toFixed(1)}TB`
}

// Attachment markers the backend appends to the prompt, keyed by the label it
// emitted (see the workspace_ref branch in web_channel.post_message). History
// only persists the prompt text, so this is the only way back to a chip.
const MARKER_TYPES: Record<string, Attachment['file_type'] | 'workspace_dir'> = {
  工作空间文件: 'workspace_ref', 工作空间檔案: 'workspace_ref', 'Workspace file': 'workspace_ref',
  工作空间目录: 'workspace_dir', 工作空间目錄: 'workspace_dir', 'Workspace directory': 'workspace_dir',
  图片: 'image', 圖片: 'image', Image: 'image',
  视频: 'video', 影片: 'video', Video: 'video',
  目录: 'directory', 目錄: 'directory', Directory: 'directory',
  文件: 'file', 檔案: 'file', File: 'file',
}

/**
 * Split trailing `[label: path]` lines off a persisted user message.
 * Returns the remaining text plus the attachments they describe.
 */
export function parseAttachmentMarkers(content: string): {
  text: string
  attachments: Attachment[] | undefined
} {
  const lines = (content || '').split('\n')
  const found: { type: string; path: string }[] = []
  for (;;) {
    if (!lines.length) break
    const line = lines[lines.length - 1].trim()
    if (!line) {
      lines.pop()
      continue
    }
    const m = line.match(/^\[([^\]:]+):\s*(.+)\]$/)
    const type = m ? MARKER_TYPES[m[1].trim()] : undefined
    if (!m || !type) break
    found.unshift({ type, path: m[2].trim() })
    lines.pop()
  }
  if (!found.length) return { text: content, attachments: undefined }
  return {
    text: lines.join('\n').trimEnd(),
    attachments: found.map((f) => ({
      file_path: f.path,
      file_name: f.path.split(/[\\/]/).filter(Boolean).pop() || f.path,
      file_type: (f.type === 'workspace_dir' ? 'workspace_ref' : f.type) as Attachment['file_type'],
      is_dir: f.type === 'workspace_dir' || f.type === 'directory',
    })),
  }
}

