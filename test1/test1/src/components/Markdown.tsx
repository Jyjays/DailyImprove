import { useMemo } from 'react'
import { marked } from 'marked'

marked.setOptions({ gfm: true, breaks: true })

/**
 * 极轻量消毒：内容来源是本地 md 与 LLM 输出，
 * 只需挡掉脚本标签、事件属性与 javascript: 协议即可。
 */
function sanitize(html: string): string {
  return html
    .replace(/<\s*(script|iframe|object|embed|style|link|meta)\b[\s\S]*?<\s*\/\s*\1\s*>/gi, '')
    .replace(/<\s*(script|iframe|object|embed|style|link|meta)\b[^>]*>/gi, '')
    .replace(/\son[a-z]+\s*=\s*(".*?"|'.*?'|[^\s>]+)/gi, '')
    .replace(/javascript:/gi, '')
}

interface Props {
  text: string
  /** 行内模式：只渲染加粗/代码/链接，不产生段落与块级元素 */
  inline?: boolean
  className?: string
}

export function Markdown({ text, inline = false, className = '' }: Props) {
  const html = useMemo(() => {
    const src = (text ?? '').trim()
    if (!src) return ''
    try {
      const raw = inline
        ? (marked.parseInline(src, { async: false }) as string)
        : (marked.parse(src, { async: false }) as string)
      return sanitize(raw)
    } catch {
      return ''
    }
  }, [text, inline])

  if (!html) return null
  return (
    <div
      className={`md-body ${inline ? 'md-inline' : ''} ${className}`.trim()}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}
