import { useMemo } from 'react'
import { marked } from 'marked'

marked.setOptions({ gfm: true, breaks: true })

/** 外部来源与用户回答都可含 Markdown；按元素、属性和协议允许列表重建 DOM。 */
function sanitize(html: string): string {
  const parsed = new DOMParser().parseFromString(html, 'text/html')
  const allowed = new Set(['P', 'BR', 'HR', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'STRONG', 'EM', 'DEL', 'S', 'UL', 'OL', 'LI', 'BLOCKQUOTE', 'PRE', 'CODE', 'TABLE', 'THEAD', 'TBODY', 'TR', 'TH', 'TD', 'A', 'IMG'])
  const drop = new Set(['SCRIPT', 'STYLE', 'IFRAME', 'OBJECT', 'EMBED', 'SVG', 'MATH', 'LINK', 'META', 'FORM', 'INPUT', 'BUTTON'])
  const container = document.createElement('div')
  const append = (source: Node, target: Node) => {
    if (source.nodeType === Node.TEXT_NODE) { target.appendChild(document.createTextNode(source.textContent ?? '')); return }
    if (!(source instanceof Element) || drop.has(source.tagName)) return
    if (!allowed.has(source.tagName)) { source.childNodes.forEach((child) => append(child, target)); return }
    const element = document.createElement(source.tagName.toLowerCase())
    if (source.tagName === 'A') {
      try {
        const url = new URL(source.getAttribute('href') || '', window.location.href)
        if (['http:', 'https:'].includes(url.protocol)) {
          element.setAttribute('href', url.href)
          element.setAttribute('target', '_blank')
          element.setAttribute('rel', 'noopener noreferrer')
        }
      } catch { /* 非法链接保留文字 */ }
    }
    if (source.tagName === 'IMG') {
      try {
        const url = new URL(source.getAttribute('src') || '', window.location.href)
        if (!['http:', 'https:'].includes(url.protocol)) return
        element.setAttribute('src', url.href)
        element.setAttribute('alt', source.getAttribute('alt') || '')
        element.setAttribute('loading', 'lazy')
        element.setAttribute('referrerpolicy', 'no-referrer')
      } catch { return }
    }
    source.childNodes.forEach((child) => append(child, element))
    target.appendChild(element)
  }
  parsed.body.childNodes.forEach((node) => append(node, container))
  return container.innerHTML
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
