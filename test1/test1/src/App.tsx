import { useCallback, useEffect, useState } from 'react'
import {
  BookOpen, CalendarCheck, ChevronRight, Code2, ExternalLink, GraduationCap,
  Lightbulb, Loader2, Save, Search, Tag, CheckCircle2, Circle, AlertCircle, HelpCircle,
} from 'lucide-react'
import type { CheckinStatus, CourseItem, KnowledgeItem, TodayPlan } from './lib/api'
import {
  CATEGORY_LABELS, fetchCheckin, fetchCourses, fetchKnowledge, fetchToday, saveCheckin,
} from './lib/api'
import { interviewQuestions } from './data/interview'
import { Markdown } from './components/Markdown'

type View = 'today' | 'knowledge' | 'courses' | 'practice'

const navItems: Array<{ id: View; label: string; icon: any; hint: string }> = [
  { id: 'today', label: '今日', icon: CalendarCheck, hint: '计划与打卡' },
  { id: 'knowledge', label: '知识', icon: BookOpen, hint: '论文与博客' },
  { id: 'courses', label: '课程', icon: GraduationCap, hint: '课程与资料' },
  { id: 'practice', label: '练习', icon: Code2, hint: '面经与编码' },
]

const STATUS_ICON: Record<CheckinStatus, any> = {
  done: CheckCircle2, partial: AlertCircle, todo: Circle, blocked: HelpCircle,
}
const STATUS_ORDER: CheckinStatus[] = ['done', 'partial', 'todo', 'blocked']

export default function App() {
  const [view, setView] = useState<View>('today')
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-glyph"><BookOpen size={20} /></span>
          <div>
            <strong>DailyImprove</strong>
            <span>学习台 · STUDY DESK</span>
          </div>
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
        {view === 'knowledge' && <KnowledgePage />}
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

function KnowledgePage() {
  const [items, setItems] = useState<KnowledgeItem[]>([])
  const [total, setTotal] = useState(0)
  const [q, setQ] = useState('')
  const [onlyAi, setOnlyAi] = useState(true)
  const [loading, setLoading] = useState(true)
  const [openId, setOpenId] = useState<number | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const d = await fetchKnowledge({ limit: 60, has_ai: onlyAi, q: q || undefined })
      setItems(d.items); setTotal(d.total)
    } catch { setItems([]) } finally { setLoading(false) }
  }, [q, onlyAi])

  useEffect(() => {
    const t = setTimeout(load, 250)
    return () => clearTimeout(t)
  }, [load])

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <p className="eyebrow">论文 · 博客 · 由 LLM 提炼</p>
          <h1>知识流</h1>
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
        </div>
      </header>

      {loading ? <Centered><Loader2 className="spin" size={24} /><p>加载中…</p></Centered>
        : items.length === 0 ? <Centered><p>没有匹配条目（共 {total} 条）</p></Centered>
        : (
          <div className="knowledge-grid">
            {items.map((it) => (
              <article
                key={it.id}
                className={`kcard ${openId === it.id ? 'open' : ''}`}
                onClick={() => setOpenId(openId === it.id ? null : it.id)}
              >
                <div className="kcard-top">
                  <span className="kcard-mod">{it.module || '未分类'}</span>
                  {typeof it.score === 'number' && <span className="kcard-score">{Math.round(it.score)}</span>}
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
            ))}
          </div>
        )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* 课程                                                                */
/* ------------------------------------------------------------------ */

const TRACK_LABELS: Record<string, string> = {
  'ai-infra': 'AI Infra', paper: '论文', drone: '横向',
}

function CoursesPage() {
  const [items, setItems] = useState<CourseItem[]>([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try { setItems((await fetchCourses()).items) } catch { setItems([]) } finally { setLoading(false) }
  }, [])
  useEffect(() => { load() }, [load])

  const byTrack = (t: string) => items.filter((i) => i.track === t)

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <p className="eyebrow">课程 · 课件 · 作业 · 视频</p>
          <h1>课程资料</h1>
        </div>
      </header>

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
                        <span className="course-prog">进度 {c.progress}%</span>
                      </div>
                      <div className="bar"><i style={{ width: `${c.progress}%` }} /></div>
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
