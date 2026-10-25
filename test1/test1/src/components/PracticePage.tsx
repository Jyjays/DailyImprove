import { useEffect, useRef, useState } from 'react'
import { BookOpen, ExternalLink, Plus, RefreshCw, Save } from 'lucide-react'
import type { AttemptMode, AttemptResult, BlogNode, PracticeDetail, PracticeQuestion, PracticeSummary, PracticeTopic, QuestionPayload, SourcePayload } from '../lib/api'
import { addPracticeSource, confirmPracticeSource, createPracticeQuestion, createProjectQuestions, editPracticeReference,
  fetchAttemptFeedback, fetchBlogTree, fetchPracticeDetail, fetchPracticeQuestions, fetchPracticeReviews, fetchPracticeSummary,
  fetchPracticeTopics, previewPracticeSource, savePracticeAttempt, updatePracticeReview, updatePracticeTopic } from '../lib/api'
import { Markdown } from './Markdown'

const KINDS = { open: '开放问答', algorithm: '算法原题', project: '项目追问', scenario: '场景分析' }
const RESULTS: Record<AttemptResult, string> = { independent: '独立完成', hinted: '提示后完成', understood: '参考后理解', again: '仍需再练' }
const MODES: Record<AttemptMode, string> = { oral: '口述', written: '文字回答', code: '原站 / 本地编码', read: '阅读参考' }
const SOURCE_TYPES = { interview: '面经 · 作者自述', algorithm: '算法平台原题', documentation: '技术文档依据', personal: '个人面试记录', generated: '自拟题', project: '本地项目文档' }
const TOPIC_STATUS = { candidate: '按需再看', focusing: '当前关注', comfortable: '自评较熟悉', paused: '暂缓' }
const sourceDefault = (): SourcePayload => ({ source_type: 'interview', title: '', url: '', published_on: null, verification: 'unverified', excerpt: '', note: '', company: '', position: '', hiring_type: '' })

interface AttemptDraft {
  answer: string; note: string; mode: AttemptMode; result: AttemptResult | ''; submission: string; clientId: string
}

function docPaths(nodes: BlogNode[]): Array<{ path: string; name: string }> {
  return nodes.flatMap((n) => n.type === 'dir' ? docPaths(n.children ?? []) : n.virtual ? [] : [{ path: n.path, name: n.path }])
}

function TopicCard({ topic, busy, save, practice }: { topic: PracticeTopic; busy: boolean; save: (status: PracticeTopic['status'], note: string) => void; practice: () => void }) {
  const [status, setStatus] = useState(topic.status)
  const [note, setNote] = useState(topic.note)
  useEffect(() => { setStatus(topic.status); setNote(topic.note) }, [topic.key, topic.status, topic.note])
  return <article className="card topic-card">
    <h3>{topic.name}</h3><p>{topic.description}</p>
    <a href={topic.material_url} target="_blank" rel="noreferrer">主材料：{topic.material_title} <ExternalLink size={12} /></a>
    <p className="topic-example">应用例子：{topic.example}</p>
    <p className="home-muted">先用代表题检查缺口，再决定补多少。熟悉程度由你自评。</p>
    <label>当前选择<select disabled={busy} value={status} onChange={(e) => setStatus(e.target.value as PracticeTopic['status'])}>{Object.entries(TOPIC_STATUS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
    <textarea disabled={busy} aria-label={`${topic.name}的缺口备注`} maxLength={1500} rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="可选：目前卡在哪里，想联系哪段项目经历" />
    <div className="home-actions"><button disabled={busy} onClick={() => save(status, note)}>保存选择</button><button onClick={practice}>看 {topic.question_count} 道代表题</button></div>
  </article>
}

function SourceFields({ value, setValue, busy, preview }: { value: SourcePayload; setValue: (s: SourcePayload) => void; busy: boolean; preview: () => void }) {
  const patch = (v: Partial<SourcePayload>) => setValue({ ...value, ...v })
  const external = ['interview', 'algorithm', 'documentation'].includes(value.source_type)
  return <fieldset className="practice-fields" disabled={busy}>
    <label>来源类型<select value={value.source_type} onChange={(e) => patch({ source_type: e.target.value as SourcePayload['source_type'] })}>{Object.entries(SOURCE_TYPES).filter(([k]) => k !== 'project').map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
    <label>来源标题<input required maxLength={300} value={value.title} onChange={(e) => patch({ title: e.target.value })} placeholder="原帖标题或文档名称" /></label>
    <label className="wide">原文链接{!external && '（可选）'}<input type="url" required={external} maxLength={2000} value={value.url} onChange={(e) => patch({ url: e.target.value })} /></label>
    <div className="wide home-actions"><button type="button" disabled={!value.url || busy} onClick={preview}>按需读取短摘录</button><span className="home-muted">读取失败时可手动整理，不会据搜索片段编题。</span></div>
    <label>原文日期（可选）<input type="date" value={value.published_on ?? ''} onChange={(e) => patch({ published_on: e.target.value || null })} /></label>
    <label className="verification-check"><input type="checkbox" checked={value.verification === 'user_confirmed'} onChange={(e) => patch({ verification: e.target.checked ? 'user_confirmed' : 'unverified' })} />我已阅读原文并核对题目</label>
    {value.source_type === 'interview' && <><label>公司（可选）<input maxLength={120} value={value.company} onChange={(e) => patch({ company: e.target.value })} /></label><label>岗位 / 实习或校招（可选）<input maxLength={250} value={value.position} onChange={(e) => patch({ position: e.target.value })} placeholder="数据库内核" /><select value={value.hiring_type} onChange={(e) => patch({ hiring_type: e.target.value })}><option value="">类型未注明</option><option>实习</option><option>校招</option><option>社招</option></select></label></>}
    <label className="wide">短摘录（可选，最多 400 字）<textarea rows={2} maxLength={400} value={value.excerpt} onChange={(e) => patch({ excerpt: e.target.value })} /></label>
    <label className="wide">来源说明 / 适用版本（可选）<input maxLength={1000} value={value.note} onChange={(e) => patch({ note: e.target.value })} /></label>
  </fieldset>
}

export function PracticePage({ onDocument }: { onDocument: (path: string) => void }) {
  const [tab, setTab] = useState<'bank' | 'topics' | 'reviews'>('bank')
  const [topics, setTopics] = useState<PracticeTopic[]>([])
  const [items, setItems] = useState<PracticeQuestion[]>([])
  const [reviewItems, setReviewItems] = useState<PracticeQuestion[]>([])
  const [summary, setSummary] = useState<PracticeSummary | null>(null)
  const [selected, setSelected] = useState<PracticeDetail | null>(null)
  const [filterTopic, setFilterTopic] = useState('')
  const [filterKind, setFilterKind] = useState('')
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [showImport, setShowImport] = useState(false)
  const [docs, setDocs] = useState<Array<{ path: string; name: string }>>([])
  const [document, setDocument] = useState('')
  const [source, setSource] = useState<SourcePayload>(sourceDefault)
  const [newTitle, setNewTitle] = useState('')
  const [newKind, setNewKind] = useState<QuestionPayload['kind']>('open')
  const [newPrompt, setNewPrompt] = useState('')
  const [newReference, setNewReference] = useState('')
  const [newTopic, setNewTopic] = useState('storage')
  const [roleTags, setRoleTags] = useState('')
  const requestId = useRef(0)
  const selectionId = useRef(0)
  const drafts = useRef(new Map<string, AttemptDraft>())

  async function loadBank() {
    const id = ++requestId.current
    try {
      const r = await fetchPracticeQuestions({ topic: filterTopic, kind: filterKind, q: query, page })
      if (id === requestId.current) { setItems(r.items); setTotal(r.total) }
    } catch (e) { if (id === requestId.current) setError((e as Error).message) }
    finally { if (id === requestId.current) setLoading(false) }
  }
  async function refreshOther() {
    const results = await Promise.allSettled([fetchPracticeTopics(), fetchPracticeReviews(), fetchPracticeSummary()])
    if (results[0].status === 'fulfilled') setTopics(results[0].value.items)
    if (results[1].status === 'fulfilled') setReviewItems(results[1].value.items)
    if (results[2].status === 'fulfilled') setSummary(results[2].value)
    const failed = results.find((r) => r.status === 'rejected')
    if (failed?.status === 'rejected') throw failed.reason
  }
  useEffect(() => { setLoading(true); void loadBank() }, [filterTopic, filterKind, query, page])
  useEffect(() => {
    refreshOther().catch((e) => setError((e as Error).message))
    fetchBlogTree().then((r) => setDocs(docPaths(r.tree))).catch(() => {})
  }, [])

  async function act(work: () => Promise<void>) {
    setBusy(true); setError(''); setMessage('')
    try { await work() } catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }
  async function choose(id: string) {
    const ticket = ++selectionId.current
    setError('')
    try { const detail = await fetchPracticeDetail(id); if (ticket === selectionId.current) setSelected(detail) }
    catch (e) { if (ticket === selectionId.current) setError((e as Error).message) }
  }
  const imported = () => act(async () => {
    const result = await createPracticeQuestion({ title: newTitle, kind: newKind, prompt: newPrompt,
      reference_notes: newReference, topics: newTopic ? [newTopic] : [], roles: roleTags.split(/[,，]/).map((v) => v.trim()).filter(Boolean), followups: [], source })
    setSelected(result.question); setShowImport(false)
    setNewTitle(''); setNewPrompt(''); setNewReference(''); setSource(sourceDefault())
    await Promise.all([loadBank(), refreshOther()])
    setMessage(result.created ? '题目与来源已保存。' : '已关联到已有题目，保留原题与练习记录，并补充新来源。')
  })
  const preview = () => act(async () => {
    const result = await previewPracticeSource(source.url)
    if (result.readable) setSource((s) => ({ ...s, title: s.title || result.title, excerpt: result.excerpt, verification: 'unverified' }))
    setMessage(result.message)
  })
  const makeProject = () => act(async () => {
    const r = await createProjectQuestions(document, newTopic ? [newTopic] : [])
    setMessage('已从所选文档建立三类追问模板；模板不代表成果已被核实。')
    await Promise.all([loadBank(), refreshOther()])
    if (r.items[0]) await choose(r.items[0].id)
  })
  const reload = () => act(async () => { await Promise.all([loadBank(), refreshOther()]); setMessage('练习与近况已刷新。') })
  const list = tab === 'reviews' ? reviewItems : items

  return <div className="page practice-page">
    <header className="page-head"><div><p className="eyebrow">真实出处 · 主动练习 · 按需复习</p><h1>练习与基础</h1></div><div className="home-actions"><button className="text-button" disabled={busy} onClick={reload}><RefreshCw size={15} /> 刷新</button><button className="primary-button" onClick={() => setShowImport(!showImport)}><Plus size={16} /> 添加题目</button></div></header>
    {error && <div className="home-error" role="alert">{error}</div>}
    {message && <div className="toast" role="status">{message}</div>}
    <div className="practice-tabs" role="tablist" aria-label="练习页面"><button role="tab" aria-selected={tab === 'bank'} onClick={() => setTab('bank')}>题目</button><button role="tab" aria-selected={tab === 'topics'} onClick={() => setTab('topics')}>基础地图</button><button role="tab" aria-selected={tab === 'reviews'} onClick={() => setTab('reviews')}>复习候选</button></div>

    {showImport && <section className="card"><h3>从来源整理一道题</h3><p className="card-sub">保存必要索引与自己的概述。未核验来源仍可保留，暂不把它当成已确认真题。</p>
      <form onSubmit={(e) => { e.preventDefault(); void imported() }}>
        <fieldset className="practice-fields" disabled={busy}>
          <label>题目标题<input required maxLength={300} value={newTitle} onChange={(e) => setNewTitle(e.target.value)} /></label>
          <label>练习类型<select value={newKind} onChange={(e) => setNewKind(e.target.value as QuestionPayload['kind'])}><option value="open">开放问答</option><option value="algorithm">算法原题</option><option value="scenario">场景分析</option></select></label>
          <label>关联基础<select value={newTopic} onChange={(e) => setNewTopic(e.target.value)}><option value="">暂不关联</option>{topics.map((t) => <option key={t.key} value={t.key}>{t.name}</option>)}</select></label>
          <label>岗位标签（逗号分隔，可选）<input maxLength={500} value={roleTags} onChange={(e) => setRoleTags(e.target.value)} /></label>
          <label className="wide">自己的题干概述<textarea required rows={3} maxLength={4000} value={newPrompt} onChange={(e) => setNewPrompt(e.target.value)} /></label>
          <label className="wide">自己整理的参考要点（可选）<textarea rows={2} maxLength={6000} value={newReference} onChange={(e) => setNewReference(e.target.value)} /></label>
        </fieldset>
        <SourceFields value={source} setValue={setSource} busy={busy} preview={preview} />
        <div className="home-actions"><button type="submit" className="primary-button" disabled={busy}>保存题目与来源</button></div>
      </form>
    </section>}

    <details className="card home-details"><summary>从已有项目文档建立追问</summary><p className="home-muted">选择现有笔记，生成设计取舍、测量证据、边界三类自拟模板。项目内容继续在文档区维护。</p><div className="practice-fields"><label>已有文档<select value={document} onChange={(e) => setDocument(e.target.value)}><option value="">请选择文档</option>{docs.map((d) => <option key={d.path} value={d.path}>{d.name}</option>)}</select></label><label>关联基础<select value={newTopic} onChange={(e) => setNewTopic(e.target.value)}><option value="">暂不关联</option>{topics.map((t) => <option key={t.key} value={t.key}>{t.name}</option>)}</select></label></div><div className="home-actions"><button disabled={busy || !document} onClick={makeProject}>建立追问模板</button></div>{!docs.length && <p className="home-muted">暂时没有可选文档，请先在文档区整理或导入材料。</p>}</details>

    {tab === 'topics' && <div className="topic-grid">{topics.map((t) => <TopicCard key={t.key} topic={t} busy={busy}
      save={(status, note) => void act(async () => { await updatePracticeTopic(t.key, status, note); await refreshOther(); setMessage('已保存你的主题选择。') })}
      practice={() => { setFilterTopic(t.key); setPage(1); setTab('bank') }} />)}</div>}
    <div hidden={tab === 'topics'} className="practice-layout">
      <section className="card question-bank">
        {tab === 'bank' ? <><form className="question-filters" onSubmit={(e) => { e.preventDefault(); setPage(1); setQuery(search) }}>
          <input aria-label="搜索题目" placeholder="搜索标题" maxLength={200} value={search} onChange={(e) => setSearch(e.target.value)} />
          <select aria-label="按基础主题筛选" value={filterTopic} onChange={(e) => { setFilterTopic(e.target.value); setPage(1) }}><option value="">全部主题</option>{topics.map((t) => <option key={t.key} value={t.key}>{t.name}</option>)}</select>
          <select aria-label="按题型筛选" value={filterKind} onChange={(e) => { setFilterKind(e.target.value); setPage(1) }}><option value="">全部题型</option>{Object.entries(KINDS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select><button type="submit">搜索</button>
        </form><p className="home-muted">共 {total} 道。自拟题与真实面经分开标注，不宣称近期高频。</p></> : <><h3>最多三道复习候选</h3><p className="home-muted">可以推迟或暂停，也可以直接去学新题。不需要清空积压。</p></>}
        {loading && tab === 'bank' ? <p>正在读取题目…</p> : !list.length ? <p className="home-muted">这里暂时没有题目。可以切换筛选或添加原题链接。</p> : <div className="question-list">{list.map((q) => <button disabled={busy} key={q.id} className={selected?.id === q.id ? 'active' : ''} onClick={() => void choose(q.id)}><span>{KINDS[q.kind]}{q.origin === 'generated' ? ' · 自拟' : ''}</span><strong>{q.title}</strong><small>{q.last_result ? `上次自评：${RESULTS[q.last_result]}` : '尚无尝试记录'}</small>{q.sources.some((s) => s.verification === 'unverified') && <small>包含待核验来源</small>}</button>)}</div>}
        {tab === 'bank' && total > 30 && <div className="home-actions"><button disabled={page === 1} onClick={() => setPage(page - 1)}>上一页</button><span>{page} / {Math.ceil(total / 30)}</span><button disabled={page * 30 >= total} onClick={() => setPage(page + 1)}>下一页</button></div>}
      </section>
      {selected ? <QuestionWorkspace key={selected.id} detail={selected} busy={busy} act={act} topics={topics} onDocument={onDocument} drafts={drafts.current}
        changed={async (next) => { setSelected(next); await Promise.all([loadBank(), refreshOther()]) }} />
        : <section className="card"><h3>选一道题，先自己想一想</h3><p>可以口述、写下来，或去原站编码。参考要点按需展开；学习记录与复习都由你主动决定。</p></section>}
    </div>
    {summary && <details className="card home-details"><summary>练习回顾 · 近七天 {summary.attempts_last_7_days} 次自愿记录</summary><p className="home-muted">{summary.note} 下方显示最近十次保存记录，日期可能早于七天。</p>{summary.recent_attempts.map((a) => <button disabled={busy} className="summary-attempt" key={a.id} onClick={() => { setTab('bank'); void choose(a.question_id) }}>{a.date.slice(0, 10)} · {a.title} · {MODES[a.mode]} · {RESULTS[a.result]}{a.note && <span>{a.note}</span>}</button>)}</details>}
  </div>
}

function QuestionWorkspace({ detail, busy, act, changed, topics, onDocument, drafts }: {
  detail: PracticeDetail; busy: boolean; act: (work: () => Promise<void>) => Promise<void>
  changed: (q: PracticeDetail) => Promise<void>; topics: PracticeTopic[]; onDocument: (path: string) => void
  drafts: Map<string, AttemptDraft>
}) {
  const cached = drafts.get(detail.id)
  const [answer, setAnswer] = useState(cached?.answer ?? '')
  const [note, setNote] = useState(cached?.note ?? '')
  const [mode, setMode] = useState<AttemptMode>(cached?.mode ?? (detail.kind === 'algorithm' ? 'code' : 'oral'))
  const [result, setResult] = useState<AttemptResult | ''>(cached?.result ?? '')
  const [submission, setSubmission] = useState(cached?.submission ?? '')
  const [reference, setReference] = useState(detail.reference_notes)
  const [source, setSource] = useState<SourcePayload>(sourceDefault)
  const [feedbackMessage, setFeedbackMessage] = useState('')
  const clientId = useRef(cached?.clientId ?? crypto.randomUUID())
  useEffect(() => {
    drafts.set(detail.id, { answer, note, mode, result, submission, clientId: clientId.current })
  }, [answer, note, mode, result, submission, detail.id, drafts])
  const edit = (f: () => void) => { f(); clientId.current = crypto.randomUUID() }
  useEffect(() => setReference(detail.reference_notes), [detail.reference_notes])
  const save = () => act(async () => {
    if (!result) return
    const saved = await savePracticeAttempt(detail.id, { client_id: clientId.current, mode, result, answer, note, submission_url: submission })
    // 记录已落盘后只更新自己的草稿；后续刷新失败不再次提交。
    setAnswer(''); setNote(''); setSubmission(''); setResult(''); clientId.current = crypto.randomUUID()
    await changed(saved.question)
  })
  const review = (action: 'postpone' | 'pause' | 'resume', days = 3) => act(async () => { await updatePracticeReview(detail.id, action, days); await changed(await fetchPracticeDetail(detail.id)) })
  const feedback = (id: number) => act(async () => {
    const r = await fetchAttemptFeedback(id)
    setFeedbackMessage(r.message || 'AI 反馈已保存，仅作为复盘参考。')
    await changed(await fetchPracticeDetail(detail.id))
  })
  return <section className="card question-workspace">
    <p className="eyebrow">{KINDS[detail.kind]} · {detail.origin === 'generated' ? '自拟 / 模板' : detail.origin === 'author' ? '作者自述面经' : '题目索引'}</p>
    <h2>{detail.title}</h2><Markdown text={detail.prompt} />{feedbackMessage && <p role="status">{feedbackMessage}</p>}
    <div className="question-topics">{detail.topics.map((key) => <span key={key}>{topics.find((t) => t.key === key)?.name || key}</span>)}</div>
    {detail.roles.length > 0 && <p className="home-muted">整理标签：{detail.roles.join('、')}</p>}
    {detail.document_path && <button className="text-button" onClick={() => onDocument(detail.document_path)}><BookOpen size={15} /> 打开关联文档</button>}
    <details className="source-details"><summary>来源与核验状态 · {detail.sources.length} 条</summary>{detail.sources.map((s) => <article key={s.id}>
      <strong>{SOURCE_TYPES[s.source_type]}</strong><p>{s.url ? <a href={s.url} target="_blank" rel="noreferrer">{s.title} <ExternalLink size={12} /></a> : s.title}</p>
      <p className="home-muted">原文日期：{s.published_on || '未注明'} · 收录：{s.captured_at.slice(0, 10)} · {s.verification === 'checked' ? '已核验出处（见说明）' : s.verification === 'user_confirmed' ? '用户已核对' : '待核验'}</p>
      {(s.company || s.position || s.hiring_type) && <p>{[s.company, s.position, s.hiring_type].filter(Boolean).join(' · ')}</p>}
      {s.note && <p className="home-muted">{s.note}</p>}{s.excerpt && <blockquote>{s.excerpt}</blockquote>}
      {s.verification === 'unverified' && <button disabled={busy} onClick={() => void act(async () => { await confirmPracticeSource(s.id); await changed(await fetchPracticeDetail(detail.id)) })}>我已核对原文</button>}
    </article>)}</details>
    {detail.kind === 'algorithm' && <div className="home-actions">{detail.sources.filter((s) => s.source_type === 'algorithm' && s.url).slice(0, 2).map((s) => <a className="primary-button" key={s.id} href={s.url} target="_blank" rel="noreferrer">去原站编码 / 判题 <ExternalLink size={15} /></a>)}</div>}
    <details className="reference-details"><summary>展开整理参考与追问</summary><p className="home-muted">下列内容是整理参考，不是企业或平台官方答案。阅读解析不等于已经掌握。</p><Markdown text={detail.reference_notes || '尚无整理参考。可以在原文核对后补充，或先记录卡点。'} /><ul>{detail.followups.map((f, i) => <li key={i}>{f}</li>)}</ul></details>
    <form className="attempt-form" onSubmit={(e) => { e.preventDefault(); void save() }}>
      <h3>保存一次尝试（可选）</h3>
      <fieldset className="practice-fields" disabled={busy}>
        <label>方式<select value={mode} onChange={(e) => edit(() => { setMode(e.target.value as AttemptMode); setResult('') })}>{Object.entries(MODES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
        <label>这次的自评<select required value={result} onChange={(e) => edit(() => setResult(e.target.value as AttemptResult))}><option value="">请选择实际情况</option>{Object.entries(RESULTS).filter(([k]) => mode !== 'read' || ['understood', 'again'].includes(k)).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
        <label className="wide">自己的回答（可选，口述可以留空）<textarea maxLength={6000} rows={4} value={answer} onChange={(e) => edit(() => setAnswer(e.target.value))} /></label>
        <label className="wide">一句卡点或复盘（可选）<textarea maxLength={2000} rows={2} value={note} onChange={(e) => edit(() => setNote(e.target.value))} /></label>
        <label className="wide">提交 / 产出链接（可选）<input type="url" maxLength={2000} value={submission} onChange={(e) => edit(() => setSubmission(e.target.value))} /></label>
        <div className="wide home-actions"><button type="submit" className="primary-button" disabled={!result || busy}><Save size={16} /> 保存尝试</button><span className="home-muted">自评不构成能力认证。</span></div>
      </fieldset>
    </form>
    <div className="review-controls"><p>复习：{detail.review ? `${detail.review.due_on} · ${detail.review.status === 'paused' ? '已暂停' : '可调整'}` : '尚未安排；保存尝试后会给出候选日期。'}</p>
      <div className="home-actions"><button disabled={busy} onClick={() => void review('postpone', 1)}>推迟一天</button><button disabled={busy} onClick={() => void review('postpone', 3)}>推迟三天</button><button disabled={busy} onClick={() => void review(detail.review?.status === 'paused' ? 'resume' : 'pause')}>{detail.review?.status === 'paused' ? '恢复复习' : '暂停此题复习'}</button></div></div>
    <details className="home-details"><summary>最近尝试 · {detail.attempts.length} 条</summary><p className="home-muted">文字反馈只在你主动请求时提交给已配置的 AI；仅提供覆盖、遗漏和追问，不评分。</p>{detail.attempts.map((a) => <article className="attempt-history" key={a.id}><strong>{a.created_at.slice(0, 16).replace('T', ' ')} · {MODES[a.mode]} · {RESULTS[a.result]}</strong>{a.note && <p>{a.note}</p>}{a.answer && <details><summary>自己的回答</summary><Markdown text={a.answer} /></details>}{a.submission_url && <a target="_blank" rel="noreferrer" href={a.submission_url}>查看提交</a>}{a.answer && <button disabled={busy} onClick={() => void feedback(a.id)}>请求 AI 复盘反馈</button>}{a.feedback && <div className="feedback-panel">{([['covered', '已覆盖'], ['missing', '可补充'], ['followups', '可追问']] as const).map(([key, label]) => <div key={key}><strong>{label}</strong><ul>{a.feedback![key].map((v, i) => <li key={i}>{v}</li>)}</ul></div>)}<p>{a.feedback.caveat}</p></div>}</article>)}</details>
    <details className="home-details"><summary>补充或更正整理参考</summary><textarea disabled={busy} maxLength={6000} rows={4} aria-label="整理参考要点" value={reference} onChange={(e) => setReference(e.target.value)} /><button disabled={busy} onClick={() => void act(async () => { await changed(await editPracticeReference(detail.id, reference)) })}>保存参考要点</button></details>
    <details className="home-details"><summary>为同一题补充来源</summary><form onSubmit={(e) => { e.preventDefault(); void act(async () => { await changed(await addPracticeSource(detail.id, source)); setSource(sourceDefault()) }) }}><SourceFields value={source} setValue={setSource} busy={busy} preview={() => void act(async () => { const p = await previewPracticeSource(source.url); if (p.readable) setSource((s) => ({ ...s, title: s.title || p.title, excerpt: p.excerpt, verification: 'unverified' })); setFeedbackMessage(p.message) })} /><button type="submit" disabled={busy}>关联这条来源</button></form></details>
  </section>
}
