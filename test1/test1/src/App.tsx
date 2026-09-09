import { useCallback, useEffect, useState } from 'react'
import {
  BookOpen, CalendarCheck, ChevronDown, ChevronLeft, ChevronRight, Code2, Edit3,
  ExternalLink, Eye, FilePlus, FileText, Folder, FolderOpen, FolderPlus, GraduationCap,
  Lightbulb, Link2, Loader2, Lock, Newspaper, PanelLeftClose, PanelLeftOpen, PenLine,
  Pencil, Rss, Save, Search, Star, Tag, Trash2, CheckCircle2, Circle, AlertCircle,
  HelpCircle,
} from 'lucide-react'
import type {
  BlogDoc, BlogNode, CheckinStatus, CourseItem, KnowledgeItem, KnowledgeKind,
  KnowledgeResult, TodayPlan,
} from './lib/api'
import {
  CATEGORY_LABELS, createBlogFolder, deleteBlogNode, fetchBlogDoc, fetchBlogTree,
  fetchCheckin, fetchCourses, fetchKnowledge, fetchNote, fetchToday, renameBlogNode,
  saveBlogDoc, saveCheckin, saveNote, toggleFavorite, updateCourse,
} from './lib/api'
import { interviewQuestions } from './data/interview'
import { Markdown } from './components/Markdown'

type View = 'today' | 'knowledge' | 'favorites' | 'blog' | 'courses' | 'practice'

const navItems: Array<{ id: View; label: string; icon: any; hint: string }> = [
  { id: 'today', label: '今日', icon: CalendarCheck, hint: '计划与打卡' },
  { id: 'knowledge', label: '知识', icon: BookOpen, hint: '论文 · 新闻 · 博客' },
  { id: 'favorites', label: '收藏', icon: Star, hint: '重点条目' },
  { id: 'blog', label: '博客', icon: PenLine, hint: '笔记与知识库' },
  { id: 'courses', label: '课程', icon: GraduationCap, hint: '课程与资料' },
  { id: 'practice', label: '练习', icon: Code2, hint: '面经与编码' },
]

/** 知识类型 -> 中文标签与图标 */
const KIND_META: Record<KnowledgeKind, { label: string; icon: any }> = {
  paper: { label: '论文', icon: FileText },
  news: { label: '新闻', icon: Newspaper },
  blog: { label: '博客', icon: Rss },
}
const KIND_ORDER: Array<KnowledgeKind | 'all'> = ['all', 'paper', 'news', 'blog']

const STATUS_ICON: Record<CheckinStatus, any> = {
  done: CheckCircle2, partial: AlertCircle, todo: Circle, blocked: HelpCircle,
}
const STATUS_ORDER: CheckinStatus[] = ['done', 'partial', 'todo', 'blocked']

export default function App() {
  const [view, setView] = useState<View>('today')
  // 从知识卡片跳到博客时，指定要打开的文档路径
  const [blogTarget, setBlogTarget] = useState<string | null>(null)
  // 全局左侧导航栏是否折叠
  const [navCollapsed, setNavCollapsed] = useState(false)

  /** 打开（必要时先创建）某条知识的笔记，然后切到博客页 */
  const openNote = async (it: KnowledgeItem) => {
    const n = await fetchNote(it.id)
    if (!n.exists) await saveNote(it.id, '')
    setBlogTarget(n.path)
    setView('blog')
  }

  return (
    <div className={`app-shell ${navCollapsed ? 'nav-collapsed' : ''}`}>
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-glyph"><BookOpen size={20} /></span>
          <div className="brand-text">
            <strong>DailyImprove</strong>
            <span>学习台 · STUDY DESK</span>
          </div>
          <button
            type="button"
            className="sidebar-collapse"
            onClick={() => setNavCollapsed((v) => !v)}
            title={navCollapsed ? '展开侧栏' : '折叠侧栏'}
          >
            {navCollapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
          </button>
        </div>
        <nav className="main-nav">
          <p className="eyebrow">工作区</p>
          {navItems.map(({ id, label, icon: Icon, hint }) => (
            <button key={id} className={view === id ? 'active' : ''} onClick={() => setView(id)}>
              <Icon size={19} /><span>{label}</span>
              {view === id && <span className="nav-mark" />}
              <em className="nav-hint">{hint}</em>
            </button>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div><Lightbulb size={14} /><span>数据来自 DailyImprove</span></div>
          <p>打卡会同时写入数据库与 plan/daily/ 日报</p>
        </div>
      </aside>
      <main className="main">
        {view === 'today' && <TodayPage />}
        {view === 'knowledge' && <KnowledgePage onNote={openNote} />}
        {view === 'favorites' && <KnowledgePage favoriteOnly onNote={openNote} />}
        {view === 'blog' && <BlogPage target={blogTarget} onTargetOpened={() => setBlogTarget(null)} />}
        {view === 'courses' && <CoursesPage />}
        {view === 'practice' && <PracticePage />}
      </main>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* 今日：计划 + 打卡（落盘到数据库与 md）                                */
/* ------------------------------------------------------------------ */

interface Row {
  category: string
  title: string
  status: CheckinStatus
  note: string
}

function TodayPage() {
  const [plan, setPlan] = useState<TodayPlan | null>(null)
  const [rows, setRows] = useState<Row[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [t, c] = await Promise.all([fetchToday(), fetchCheckin()])
      setPlan(t)
      // 以日报 md 的打卡清单为骨架，用数据库里已存的状态/说明覆盖
      const saved = new Map(c.items.map((i) => [i.category, i]))
      const merged: Row[] = (t.checklist.length ? t.checklist : []).map((cl) => {
        const cat = matchCategory(cl.text)
        const s = saved.get(cat)
        return {
          category: cat,
          title: cl.text,
          status: s?.status ?? cl.status,
          note: s?.note ?? '',
        }
      })
      setRows(merged.length ? merged : defaultRows())
    } catch (e) {
      setMsg(`加载失败：${(e as Error).message}`)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const patch = (category: string, next: Partial<Row>) =>
    setRows((cur) => cur.map((r) => (r.category === category ? { ...r, ...next } : r)))

  const persist = async () => {
    if (!plan) return
    setSaving(true)
    setMsg('')
    try {
      const res = await saveCheckin(plan.date, rows.map((r) => ({
        category: r.category, title: r.title, status: r.status, note: r.note,
      })))
      setMsg(res.md_written
        ? `已保存，并回写 ${res.md_file}`
        : '已存入数据库（日报文件未找到，未回写 md）')
    } catch (e) {
      setMsg(`保存失败：${(e as Error).message}`)
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <Centered><Loader2 className="spin" size={26} /><p>加载今日计划…</p></Centered>

  const date = plan?.date ?? new Date().toISOString().slice(0, 10)

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <p className="eyebrow">{date} · 今日计划与打卡</p>
          <h1>今天做到哪一步</h1>
        </div>
        <button className="primary-button" onClick={persist} disabled={saving}>
          {saving ? <Loader2 className="spin" size={16} /> : <Save size={16} />}
          {saving ? '保存中' : '保存打卡'}
        </button>
      </header>

      {msg && <div className="toast">{msg}</div>}

      {plan?.commit && (
        <section className="card brief ghost">
          <h3><ChevronRight size={15} /> 昨日承诺</h3>
          <Markdown text={plan.commit} />
        </section>
      )}

      {plan?.summary && (
        <section className="card brief">
          <h3><Lightbulb size={15} /> 昨日结果</h3>
          <Markdown text={plan.summary} />
        </section>
      )}

      <section className="card">
        <h3>今日三件事</h3>
        {plan?.plan_table?.rows?.length ? (
          <div className="plan-cards">
            {plan.plan_table.rows.map((cells, i) => (
              <article className="plan-card" key={i}>
                {cells.map((cell, j) => (
                  <div className="plan-cell" key={j}>
                    <span className="plan-label">
                      {plan.plan_table.headers[j] ?? ''}
                    </span>
                    <Markdown inline text={cell} />
                  </div>
                ))}
              </article>
            ))}
          </div>
        ) : plan?.plan_raw ? (
          <Markdown text={plan.plan_raw} />
        ) : (
          <p className="card-sub">今天的日报还没有生成计划。</p>
        )}
      </section>

      <section className="card">
        <h3>打卡</h3>
        <p className="card-sub">
          四档状态：<code>[x]</code> 已完成 · <code>[!]</code> 部分完成（跨天延续）·{' '}
          <code>[ ]</code> 未做 · <code>[?]</code> 卡住。说明会一并写进日报。
        </p>
        <div className="checkin-list">
          {rows.map((r) => (
            <div key={r.category} className={`checkin-row ${r.status}`}>
              <div className="checkin-main">
                <span className="checkin-tag">{CATEGORY_LABELS[r.category] ?? r.category}</span>
                <Markdown inline className="checkin-title" text={stripMarks(r.title)} />
              </div>
              <div className="status-group">
                {STATUS_ORDER.map((s) => {
                  const SI = STATUS_ICON[s]
                  return (
                    <button
                      key={s}
                      className={`status-btn ${s} ${r.status === s ? 'on' : ''}`}
                      onClick={() => patch(r.category, { status: s })}
                      title={s}
                    >
                      <SI size={14} />
                    </button>
                  )
                })}
              </div>
              <textarea
                className="checkin-note"
                placeholder="特殊说明 / 卡点（会写入日报）"
                value={r.note}
                onChange={(e) => patch(r.category, { note: e.target.value })}
              />
            </div>
          ))}
        </div>
      </section>

      {plan?.tomorrow && (
        <section className="card brief alt">
          <h3><ChevronRight size={15} /> 明日预告</h3>
          <Markdown text={plan.tomorrow} />
        </section>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* 知识：论文 / 博客卡片流                                              */
/* ------------------------------------------------------------------ */

const PAGE_SIZE = 12
const DAY_OPTIONS = [
  { value: 7, label: '近 7 天' },
  { value: 14, label: '近 14 天' },
  { value: 30, label: '近 30 天' },
  { value: 0, label: '全部' },
]

function KnowledgePage({
  favoriteOnly = false,
  onNote,
}: {
  favoriteOnly?: boolean
  onNote?: (it: KnowledgeItem) => void
}) {
  const [data, setData] = useState<KnowledgeResult | null>(null)
  const [kind, setKind] = useState<KnowledgeKind | 'all'>('all')
  const [q, setQ] = useState('')
  const [onlyAi, setOnlyAi] = useState(true)
  const [days, setDays] = useState(7)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [openId, setOpenId] = useState<number | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)

  // 收藏页不受时间窗限制：days=0
  const load = useCallback(async () => {
    setLoading(true)
    try {
      setData(await fetchKnowledge({
        kind,
        q: q || undefined,
        has_ai: onlyAi,
        favorite: favoriteOnly,
        days: favoriteOnly ? 0 : days,
        page,
        page_size: PAGE_SIZE,
      }))
    } catch { setData(null) } finally { setLoading(false) }
  }, [kind, q, onlyAi, days, page, favoriteOnly])

  useEffect(() => {
    const t = setTimeout(load, q ? 250 : 0)
    return () => clearTimeout(t)
  }, [load])

  // 筛选条件一变就回到第一页，否则会停在一个不存在的页码上
  useEffect(() => { setPage(1) }, [kind, q, onlyAi, days, favoriteOnly])

  /** 收藏切换：先本地乐观更新，失败再整体重载回滚 */
  const fav = async (it: KnowledgeItem) => {
    const next = !it.is_favorite
    setData((d) => d && {
      ...d,
      favorite_count: Math.max(0, d.favorite_count + (next ? 1 : -1)),
      items: d.items.map((x) => (x.id === it.id ? { ...x, is_favorite: next } : x)),
    })
    setBusyId(it.id)
    try {
      await toggleFavorite(it.id)
      if (favoriteOnly) await load()   // 收藏页里取消收藏后要移出列表
    } catch {
      await load()
    } finally { setBusyId(null) }
  }

  const counts = data?.kind_counts ?? {}
  const items = data?.items ?? []
  const totalPages = data?.total_pages ?? 1

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <p className="eyebrow">
            {favoriteOnly
              ? `收藏 · ${data?.favorite_count ?? 0} 条 · 不受更新时间影响`
              : '论文 · 新闻 · 博客 · 由 LLM 提炼'}
          </p>
          <h1>{favoriteOnly ? '我的收藏' : '知识流'}</h1>
        </div>
        <div className="filters">
          <label className="search">
            <Search size={15} />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="搜索标题 / 摘要 / 标签" />
          </label>
          <label className="switch">
            <input type="checkbox" checked={onlyAi} onChange={(e) => setOnlyAi(e.target.checked)} />
            只看有 AI 摘要的
          </label>
          {!favoriteOnly && (
            <select className="days-select" value={days} onChange={(e) => setDays(Number(e.target.value))}>
              {DAY_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          )}
        </div>
      </header>

      <div className="kind-tabs">
        {KIND_ORDER.map((k) => {
          const meta = k === 'all' ? null : KIND_META[k]
          const Icon = meta?.icon
          const n = k === 'all' ? (counts.all ?? 0) : (counts[k] ?? 0)
          return (
            <button
              key={k}
              className={`kind-tab ${kind === k ? 'on' : ''}`}
              onClick={() => setKind(k)}
            >
              {Icon ? <Icon size={14} /> : null}
              {meta?.label ?? '全部'}
              <em>{n}</em>
            </button>
          )
        })}
      </div>

      {loading ? <Centered><Loader2 className="spin" size={24} /><p>加载中…</p></Centered>
        : items.length === 0 ? (
          <Centered>
            <p>没有匹配条目（共 {data?.total ?? 0} 条）</p>
            {favoriteOnly && <p className="dim">在知识流里点卡片右上角的星标即可收藏。</p>}
          </Centered>
        ) : (
          <>
            <div className="knowledge-grid">
              {items.map((it) => {
                const meta = KIND_META[it.kind] ?? KIND_META.blog
                const KIcon = meta.icon
                return (
                  <article
                    key={it.id}
                    className={`kcard ${openId === it.id ? 'open' : ''}`}
                    onClick={() => setOpenId(openId === it.id ? null : it.id)}
                  >
                    <div className="kcard-top">
                      <span className={`kind-chip ${it.kind}`}>
                        <KIcon size={12} />{meta.label}
                      </span>
                      <span
                        className="kcard-date"
                        title={it.date_source === 'published' ? '发布时间' : '入库时间'}
                      >
                        {it.date ?? '—'}
                        {it.date_source === 'fetched' && <em>入库</em>}
                      </span>
                      <span className="kcard-gap" />
                      {typeof it.score === 'number' && <span className="kcard-score">{Math.round(it.score)}</span>}
                      {onNote && (
                        <button
                          type="button"
                          className="icon-btn"
                          title="写笔记（存到博客）"
                          onClick={(e) => { e.stopPropagation(); onNote(it) }}
                        >
                          <PenLine size={14} />
                        </button>
                      )}
                      <button
                        type="button"
                        className={`star-btn ${it.is_favorite ? 'on' : ''}`}
                        title={it.is_favorite ? '取消收藏' : '收藏'}
                        disabled={busyId === it.id}
                        onClick={(e) => { e.stopPropagation(); fav(it) }}
                      >
                        <Star size={15} fill={it.is_favorite ? 'currentColor' : 'none'} />
                      </button>
                    </div>

                    <h3>{it.title}</h3>

                    {it.ai_summary
                      ? <Markdown className="kcard-summary" text={it.ai_summary} />
                      : <p className="kcard-summary empty">暂无 AI 摘要</p>}

                    {it.reason && <p className="kcard-reason"><Lightbulb size={13} /> {it.reason}</p>}

                    {it.tags?.length > 0 && (
                      <div className="kcard-tags">
                        {it.tags.map((t) => <span key={t}><Tag size={11} />{t}</span>)}
                      </div>
                    )}

                    {openId === it.id && (
                      <div className="kcard-body">
                        <p className="kcard-source">来源：{it.source_name || it.module || '—'}</p>
                        {it.body_excerpt && <p className="kcard-excerpt">{it.body_excerpt}</p>}
                        {it.origin_summary && (
                          <details>
                            <summary>原文摘要</summary>
                            <p>{it.origin_summary}</p>
                          </details>
                        )}
                      </div>
                    )}

                    {it.url && (
                      <a className="kcard-link" href={it.url} target="_blank" rel="noreferrer"
                         onClick={(e) => e.stopPropagation()}>
                        深入阅读原文 <ExternalLink size={13} />
                      </a>
                    )}
                  </article>
                )
              })}
            </div>

            {totalPages > 1 && (
              <nav className="pager">
                <button type="button" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                  <ChevronLeft size={15} /> 上一页
                </button>
                <span>
                  第 <b>{data?.page ?? 1}</b> / {totalPages} 页 · 共 {data?.total ?? 0} 条
                </span>
                <button type="button" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
                  下一页 <ChevronRight size={15} />
                </button>
              </nav>
            )}
          </>
        )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* 博客：本地 md 文档树 + 收藏笔记                                       */
/* ------------------------------------------------------------------ */

const NEW_DOC_BODY = '# 新文档\n\n开始写点什么。\n'

/** 递归目录树。定义在组件外，避免每次渲染重建导致输入焦点丢失 */
function BlogTree({
  nodes, depth, expanded, active, onToggle, onOpen, onDelete,
}: {
  nodes: BlogNode[]
  depth: number
  expanded: Set<string>
  active: string | null
  onToggle: (p: string) => void
  onOpen: (p: string) => void
  onDelete: (p: string, isDir: boolean) => void
}) {
  return (
    <ul className="blog-tree" style={{ paddingLeft: depth === 0 ? 0 : 15 }}>
      {nodes.map((n) => {
        if (n.type === 'dir') {
          const isOpen = expanded.has(n.path)
          const isVirtual = n.virtual === true
          return (
            <li key={n.path}>
              <div className="blog-row">
                <button type="button" className="blog-twist" onClick={() => onToggle(n.path)}>
                  {isOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                </button>
                <button type="button" className="blog-name" onClick={() => onToggle(n.path)}>
                  {isOpen ? <FolderOpen size={14} /> : <Folder size={14} />}
                  {n.name}
                  {isVirtual && <em className="blog-virtual-tag" title="由日报系统管理，博客侧只读">只读</em>}
                </button>
                {!isVirtual && (
                  <button type="button" className="blog-del" title="删除目录（含全部内容）"
                          onClick={() => onDelete(n.path, true)}>
                    <Trash2 size={12} />
                  </button>
                )}
              </div>
              {isOpen && n.children && (
                <BlogTree
                  nodes={n.children} depth={depth + 1} expanded={expanded} active={active}
                  onToggle={onToggle} onOpen={onOpen} onDelete={onDelete}
                />
              )}
            </li>
          )
        }
        const isVirtual = n.virtual === true
        return (
          <li key={n.path}>
            <div className={`blog-row file ${active === n.path ? 'on' : ''}`}>
              <span className="blog-twist" />
              <button type="button" className="blog-name" onClick={() => onOpen(n.path)} title={n.title}>
                <FileText size={14} />{n.title}
              </button>
              {!isVirtual && (
                <button type="button" className="blog-del" title="删除文档"
                        onClick={() => onDelete(n.path, false)}>
                  <Trash2 size={12} />
                </button>
              )}
            </div>
          </li>
        )
      })}
    </ul>
  )
}

/** 收集所有目录路径，用于默认展开 */
function collectDirs(nodes: BlogNode[]): string[] {
  return nodes.flatMap((n) =>
    n.type === 'dir' ? [n.path, ...collectDirs(n.children ?? [])] : [])
}

function BlogPage({ target, onTargetOpened }: { target: string | null; onTargetOpened: () => void }) {
  const [tree, setTree] = useState<BlogNode[]>([])
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [doc, setDoc] = useState<BlogDoc | null>(null)
  const [draft, setDraft] = useState('')
  const [title, setTitle] = useState('')
  const [tags, setTags] = useState('')
  const [mode, setMode] = useState<'edit' | 'preview'>('edit')
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const [creating, setCreating] = useState<'file' | 'dir' | null>(null)
  const [newPath, setNewPath] = useState('')
  const [renaming, setRenaming] = useState(false)
  const [renameTo, setRenameTo] = useState('')
  // 博客目录树侧栏是否折叠（折叠后编辑器占满整行）
  const [sideCollapsed, setSideCollapsed] = useState(false)

  const reload = useCallback(async () => {
    try { setTree((await fetchBlogTree()).tree) } catch { setTree([]) }
  }, [])

  useEffect(() => { reload() }, [reload])

  const openDoc = useCallback(async (p: string): Promise<boolean> => {
    setBusy(true); setMsg('')
    try {
      const d = await fetchBlogDoc(p)
      setDoc(d)
      setDraft(d.content)
      setTitle(d.title)
      setTags(d.tags.join(', '))
      setDirty(false)
      setMode('edit')
      return true
    } catch {
      return false
    } finally { setBusy(false) }
  }, [])

  // 从知识卡片跳过来：文档不存在就先建一个再打开
  useEffect(() => {
    if (!target) return
    let cancelled = false
    ;(async () => {
      let ok = await openDoc(target)
      if (!ok) {
        try {
          await saveBlogDoc({ path: target, content: NEW_DOC_BODY })
          ok = await openDoc(target)
        } catch { /* 打开失败时下面统一提示 */ }
      }
      if (!cancelled) {
        if (!ok) setMsg(`打不开文档：${target}`)
        await reload()
        onTargetOpened()
      }
    })()
    return () => { cancelled = true }
  }, [target, openDoc, reload, onTargetOpened])

  // 目录结构变化时全量展开（新建/删除后重来；手动折叠会在下次结构性变更时重置）
  useEffect(() => { setExpanded(new Set(collectDirs(tree))) }, [tree])

  const save = async () => {
    if (!doc) return
    setBusy(true); setMsg('')
    try {
      const r = await saveBlogDoc({
        path: doc.path,
        content: draft,
        title,
        tags: tags.split(/[,，]/).map((s) => s.trim()).filter(Boolean),
      })
      setDirty(false)
      setMsg(`已保存 ${r.path}`)
      await openDoc(doc.path)
      await reload()
    } catch (e) {
      setMsg(`保存失败：${(e as Error).message}`)
    } finally { setBusy(false) }
  }

  const createNode = async () => {
    const p = newPath.trim().replace(/^\/+|\/+$/g, '')
    if (!p) return
    setBusy(true); setMsg('')
    try {
      if (creating === 'dir') {
        await createBlogFolder(p)
        setMsg(`已创建目录 ${p}`)
      } else {
        const fp = p.toLowerCase().endsWith('.md') ? p : `${p}.md`
        await saveBlogDoc({ path: fp, content: NEW_DOC_BODY, title: fp.split('/').pop()?.replace(/\.md$/, '') })
        await openDoc(fp)
      }
      setNewPath(''); setCreating(null)
      await reload()
    } catch (e) {
      setMsg(`创建失败：${(e as Error).message}`)
    } finally { setBusy(false) }
  }

  const remove = async (p: string, isDir: boolean) => {
    if (!window.confirm(
      `确定删除${isDir ? '目录（含其中全部文档）' : '文档'}？\n\n${p}\n\n删除后不可恢复。`
    )) return
    setBusy(true); setMsg('')
    try {
      await deleteBlogNode(p)
      if (doc?.path === p) { setDoc(null); setDraft('') }
      await reload()
    } catch (e) {
      setMsg(`删除失败：${(e as Error).message}`)
    } finally { setBusy(false) }
  }

  const doRename = async () => {
    if (!doc || !renameTo.trim()) return
    setBusy(true); setMsg('')
    try {
      const r = await renameBlogNode(doc.path, renameTo.trim())
      setRenaming(false)
      await openDoc(r.path)
      await reload()
      setMsg(`已重命名为 ${r.path}`)
    } catch (e) {
      setMsg(`重命名失败：${(e as Error).message}`)
    } finally { setBusy(false) }
  }

  const toggle = (p: string) =>
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(p)) next.delete(p); else next.add(p)
      return next
    })

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <p className="eyebrow">本地 md 文档树 · blog/ 目录即事实来源</p>
          <h1>我的博客</h1>
        </div>
        <div className="filters">
          <button type="button" className="ghost-btn" onClick={() => { setCreating('file'); setNewPath('') }}>
            <FilePlus size={14} /> 新建文档
          </button>
          <button type="button" className="ghost-btn" onClick={() => { setCreating('dir'); setNewPath('') }}>
            <FolderPlus size={14} /> 新建目录
          </button>
        </div>
      </header>

      {msg && <div className="toast">{msg}</div>}

      {creating && (
        <div className="blog-create">
          <input
            autoFocus
            value={newPath}
            onChange={(e) => setNewPath(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') createNode()
              if (e.key === 'Escape') setCreating(null)
            }}
            placeholder={creating === 'dir' ? '目录名，如 ai-infra/cuda' : '文档路径，如 ai-infra/cuda/notes.md'}
          />
          <button type="button" className="primary-button small" onClick={createNode}>创建</button>
          <button type="button" className="ghost-btn" onClick={() => setCreating(null)}>取消</button>
        </div>
      )}

      <div className={`blog-layout ${sideCollapsed ? 'side-collapsed' : ''}`}>
        <aside className="blog-side">
          <div className="blog-side-head">
            <span className="blog-side-title">目录</span>
            <button
              type="button"
              className="blog-side-collapse"
              onClick={() => setSideCollapsed((v) => !v)}
              title={sideCollapsed ? '展开目录树' : '折叠目录树'}
            >
              {sideCollapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
            </button>
          </div>
          <div className="blog-side-body">
            {tree.length === 0
              ? <p className="dim">还没有文档。点右上角「新建文档」开始。</p>
              : (
                <BlogTree
                  nodes={tree} depth={0} expanded={expanded} active={doc?.path ?? null}
                  onToggle={toggle} onOpen={(p) => openDoc(p)}
                  onDelete={(p, isDir) => remove(p, isDir)}
                />
              )}
          </div>
        </aside>

        <section className="blog-main">
          {!doc ? (
            <Centered>
              <PenLine size={22} />
              <p>从左侧选一篇文档，或新建一个</p>
              <p className="dim">收藏页点卡片上的笔图标，会自动在这里生成对应的笔记</p>
            </Centered>
          ) : (
            <>
              <div className="blog-toolbar">
                {doc.read_only ? (
                  <>
                    <input className="blog-title" value={title} placeholder="标题" readOnly />
                    <em className="blog-readonly-tag" title="由日报系统管理，博客侧只读">
                      <Lock size={12} /> 只读
                    </em>
                    <span className="kcard-gap" />
                    <button type="button" className={`ghost-btn ${mode === 'edit' ? 'on' : ''}`}
                            onClick={() => setMode('edit')}><Edit3 size={13} />查看源码</button>
                    <button type="button" className={`ghost-btn ${mode === 'preview' ? 'on' : ''}`}
                            onClick={() => setMode('preview')}><Eye size={13} />预览</button>
                  </>
                ) : (
                  <>
                    <input className="blog-title" value={title} placeholder="标题"
                           onChange={(e) => { setTitle(e.target.value); setDirty(true) }} />
                    <input className="blog-tags" value={tags} placeholder="标签，逗号分隔"
                           onChange={(e) => { setTags(e.target.value); setDirty(true) }} />
                    <span className="kcard-gap" />
                    <button type="button" className={`ghost-btn ${mode === 'edit' ? 'on' : ''}`}
                            onClick={() => setMode('edit')}><Edit3 size={13} />编辑</button>
                    <button type="button" className={`ghost-btn ${mode === 'preview' ? 'on' : ''}`}
                            onClick={() => setMode('preview')}><Eye size={13} />预览</button>
                    <button type="button" className="ghost-btn"
                            onClick={() => { setRenameTo(doc.path); setRenaming(true) }}>
                      <Pencil size={13} />重命名
                    </button>
                    <button type="button" className="ghost-btn danger" onClick={() => remove(doc.path, false)}>
                      <Trash2 size={13} />删除
                    </button>
                    <button type="button" className="primary-button" onClick={save} disabled={busy}>
                      {busy ? <Loader2 className="spin" size={14} /> : <Save size={14} />}
                      {busy ? '保存中' : '保存'}
                    </button>
                  </>
                )}
              </div>

              <p className="blog-meta">
                <code>{doc.path}</code> · 更新于 {doc.updated_at.slice(0, 16).replace('T', ' ')}
                {dirty && <em>有未保存的修改</em>}
              </p>

              {renaming && (
                <div className="blog-create">
                  <input autoFocus value={renameTo} onChange={(e) => setRenameTo(e.target.value)}
                         onKeyDown={(e) => { if (e.key === 'Enter') doRename(); if (e.key === 'Escape') setRenaming(false) }} />
                  <button type="button" className="primary-button small" onClick={doRename}>确认</button>
                  <button type="button" className="ghost-btn" onClick={() => setRenaming(false)}>取消</button>
                </div>
              )}

              {doc.item && (
                <div className="blog-ref">
                  <span className="blog-ref-label"><Link2 size={12} /> 关联知识</span>
                  <span className={`kind-chip ${doc.item.kind}`}>{KIND_META[doc.item.kind]?.label}</span>
                  <strong>{doc.item.title}</strong>
                  <span className="kcard-date">{doc.item.date}</span>
                  {doc.item.url && (
                    <a href={doc.item.url} target="_blank" rel="noreferrer">原文 <ExternalLink size={12} /></a>
                  )}
                </div>
              )}

              {mode === 'edit' ? (
                <textarea
                  className="blog-editor"
                  value={draft}
                  spellCheck={false}
                  readOnly={doc.read_only === true}
                  onChange={(e) => { setDraft(e.target.value); setDirty(true) }}
                />
              ) : (
                <div className="blog-preview"><Markdown text={draft} /></div>
              )}
            </>
          )}
        </section>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* 课程                                                                */
/* ------------------------------------------------------------------ */

const TRACK_LABELS: Record<string, string> = {
  'ai-infra': 'AI Infra', paper: '论文', drone: '横向',
}

const COURSE_STATUS = ['未开始', '进行中', '已完成', '暂停']

function CoursesPage() {
  const [items, setItems] = useState<CourseItem[]>([])
  const [loading, setLoading] = useState(true)
  const [savingId, setSavingId] = useState<number | null>(null)
  const [err, setErr] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try { setItems((await fetchCourses()).items) } catch { setItems([]) } finally { setLoading(false) }
  }, [])
  useEffect(() => { load() }, [load])

  /** 改状态或进度：PUT /api/study/courses/{id}，成功后就地更新本地列表 */
  const patch = useCallback(async (c: CourseItem, next: Partial<CourseItem>) => {
    const merged: CourseItem = { ...c, ...next }
    setSavingId(c.id)
    setErr(null)
    try {
      const { id: _drop, ...body } = merged
      await updateCourse(c.id, body)
      setItems((prev) => prev.map((x) => (x.id === c.id ? merged : x)))
    } catch (e) {
      setErr(`保存失败（课程 #${c.id}）：${(e as Error).message}`)
    } finally {
      setSavingId(null)
    }
  }, [])

  const bump = (c: CourseItem, delta: number) =>
    patch(c, { progress: Math.max(0, Math.min(100, c.progress + delta)) })

  const byTrack = (t: string) => items.filter((i) => i.track === t)

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <p className="eyebrow">课程 · 课件 · 作业 · 视频</p>
          <h1>课程资料</h1>
        </div>
      </header>

      {err && <p className="dim" style={{ color: '#a32d2d' }}>{err}</p>}

      {loading ? <Centered><Loader2 className="spin" size={24} /><p>加载中…</p></Centered>
        : items.length === 0
          ? <Centered>
              <p>课程库为空。</p>
              <p className="dim">用 POST /api/study/courses 添加，或让我从 roadmap 批量导入。</p>
            </Centered>
          : Object.keys(TRACK_LABELS).map((t) => (
              <section key={t} className="card">
                <h3>{TRACK_LABELS[t]}</h3>
                <div className="course-grid">
                  {byTrack(t).map((c) => (
                    <article key={c.id} className="course-card">
                      <div className="course-top">
                        <span className="course-phase">{c.phase || '—'}</span>
                        <span className="course-status">{c.status}</span>
                      </div>
                      <h4>{c.title}</h4>
                      {c.provider && <p className="course-provider">{c.provider}</p>}
                      {c.description && <p className="course-desc">{c.description}</p>}
                      {c.resources?.length > 0 && (
                        <ul className="course-res">
                          {c.resources.map((r, i) => (
                            <li key={i}>
                              <a href={r.url} target="_blank" rel="noreferrer">
                                {r.type && <em>{r.type}</em>}{r.name}<ExternalLink size={11} />
                              </a>
                            </li>
                          ))}
                        </ul>
                      )}
                      <div className="course-foot">
                        {c.url && <a href={c.url} target="_blank" rel="noreferrer">课程主页 <ExternalLink size={12} /></a>}
                      </div>
                      <div className="bar"><i style={{ width: `${c.progress}%` }} /></div>
                      <div className="course-ctrl">
                        <select
                          value={COURSE_STATUS.includes(c.status) ? c.status : '未开始'}
                          disabled={savingId === c.id}
                          onChange={(e) => {
                            const s = e.target.value
                            patch(c, { status: s, progress: s === '已完成' ? 100 : c.progress })
                          }}
                        >
                          {COURSE_STATUS.map((s) => <option key={s} value={s}>{s}</option>)}
                        </select>
                        <button type="button" disabled={savingId === c.id || c.progress <= 0}
                          onClick={() => bump(c, -10)} title="进度 -10%">−</button>
                        <span className="course-prog">{c.progress}%</span>
                        <button type="button" disabled={savingId === c.id || c.progress >= 100}
                          onClick={() => bump(c, 10)} title="进度 +10%">+</button>
                        {savingId === c.id && <Loader2 className="spin" size={12} />}
                      </div>
                    </article>
                  ))}
                </div>
              </section>
            ))}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* 练习：面经自测                                                       */
/* ------------------------------------------------------------------ */

function PracticePage() {
  const [idx, setIdx] = useState(0)
  const [picked, setPicked] = useState<number | null>(null)
  const [revealed, setRevealed] = useState(false)
  const q = interviewQuestions[idx]

  const next = () => {
    setIdx((i) => (i + 1) % interviewQuestions.length)
    setPicked(null); setRevealed(false)
  }

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <p className="eyebrow">面经自测 · 第 {idx + 1} / {interviewQuestions.length} 题</p>
          <h1>练习</h1>
        </div>
      </header>

      <section className="card quiz">
        <div className="quiz-meta">
          <span className="quiz-tag">{q.topic}</span>
          <span className="quiz-diff">{q.difficulty}</span>
        </div>
        <h3>{q.title}</h3>
        {q.context && <p className="quiz-context">{q.context}</p>}

        <div className="quiz-options">
          {q.options.map((o, i) => (
            <button
              key={i}
              className={`quiz-opt ${picked === i ? 'picked' : ''} ${revealed && i === q.answer ? 'right' : ''} ${revealed && picked === i && i !== q.answer ? 'wrong' : ''}`}
              onClick={() => !revealed && setPicked(i)}
              disabled={revealed}
            >
              <b>{String.fromCharCode(65 + i)}</b>{o}
            </button>
          ))}
        </div>

        <div className="quiz-actions">
          <button className="primary-button" onClick={() => setRevealed(true)} disabled={picked === null || revealed}>
            提交
          </button>
          <button className="text-button" onClick={next}>下一题 <ChevronRight size={14} /></button>
        </div>

        {revealed && (
          <div className="quiz-explain">
            <p><strong>答案 {String.fromCharCode(65 + q.answer)}</strong></p>
            <p>{q.explain}</p>
          </div>
        )}
      </section>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* 公共小组件与工具                                                      */
/* ------------------------------------------------------------------ */

function Centered({ children }: { children: React.ReactNode }) {
  return <div className="centered">{children}</div>
}

/** 把 md 的打卡行文本映射到分类 */
function matchCategory(text: string): string {
  for (const [cat, label] of Object.entries(CATEGORY_LABELS)) {
    if (text.startsWith(label)) return cat
  }
  return text.slice(0, 10) || 'other'
}

/** 去掉 md 里未填写的占位下划线 */
function stripMarks(text: string): string {
  return text.replace(/[_—–]+/g, '…').trim()
}

/** 日报不存在时的默认打卡骨架 */
function defaultRows(): Row[] {
  return Object.entries(CATEGORY_LABELS).map(([category, title]) => ({
    category, title, status: 'todo' as CheckinStatus, note: '',
  }))
}
