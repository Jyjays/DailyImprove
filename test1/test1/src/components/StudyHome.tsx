import { useEffect, useRef, useState } from 'react'
import { BookOpen, Copy, Loader2, MessageCircle, RefreshCw, Save } from 'lucide-react'
import type { BlogNode, LearningEntry, LearningProfile, SharedContext, TodayPlan } from '../lib/api'
import {
  addLearningEntry, decideGuidance, exportContext, fetchBlogTree, fetchContext,
  fetchToday, retryContextExport, updateContext,
} from '../lib/api'
import { Markdown } from './Markdown'

function documents(nodes: BlogNode[]): Array<{ path: string; name: string }> {
  return nodes.flatMap((n) => n.type === 'dir' ? documents(n.children ?? [])
    : n.path.startsWith('__virtual__:') ? [] : [{ path: n.path, name: n.path }])
}

const KIND_LABEL = { progress: '学习进展', question: '想问 AI', guidance: 'AI 建议' }
const STATUS_LABEL = { proposed: '待你决定', accepted: '已采纳', dismissed: '暂不采用', recorded: '已记录' }

export function StudyHome({ onDocument }: { onDocument: (path?: string) => void }) {
  const [context, setContext] = useState<SharedContext | null>(null)
  const [draft, setDraft] = useState<LearningProfile | null>(null)
  const [draftRevision, setDraftRevision] = useState(0)
  const [docOptions, setDocOptions] = useState<Array<{ path: string; name: string }>>([])
  const [docError, setDocError] = useState('')
  const [kind, setKind] = useState<LearningEntry['kind']>('progress')
  const [content, setContent] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [copyText, setCopyText] = useState('')
  const [allEntries, setAllEntries] = useState(false)
  const [historyDate, setHistoryDate] = useState('')
  const [history, setHistory] = useState<TodayPlan | null>(null)
  const clientId = useRef(crypto.randomUUID())

  async function load() {
    setError('')
    try {
      const next = await fetchContext()
      setContext(next)
      setDraft(next.profile)
      setDraftRevision(next.revision)
    } catch (e) { setError((e as Error).message) }
  }

  useEffect(() => {
    void load()
    fetchBlogTree().then((r) => setDocOptions(documents(r.tree)))
      .catch(() => setDocError('文档目录暂时无法加载，可以稍后再关联。'))
  }, [])

  async function act(task: () => Promise<void>) {
    setBusy(true); setError(''); setMessage('')
    try { await task() } catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }

  const saveProfile = () => act(async () => {
    if (!draft) return
    const next = await updateContext(draftRevision, draft)
    setContext(next); setDraft(next.profile); setDraftRevision(next.revision)
    setMessage('当前关注已保存。')
  })

  const refresh = () => act(async () => {
    const next = await fetchContext()
    if (draft && context && JSON.stringify(draft) === JSON.stringify(context.profile)) {
      setDraft(next.profile); setDraftRevision(next.revision)
    } else if (context && JSON.stringify(next.profile) === JSON.stringify(context.profile)) {
      setDraftRevision(next.revision)
    }
    setContext(next)
    setMessage('已读取最新交流，尚未保存的草稿会保留。')
  })

  const record = () => act(async () => {
    const next = await addLearningEntry({ client_id: clientId.current, kind,
      author: kind === 'guidance' ? 'assistant' : 'user', content })
    setContext(next)
    // 只增加交流记录时，若阶段表单未改动，跟随新版本，避免不必要的冲突。
    if (context && JSON.stringify(next.profile) === JSON.stringify(context.profile)) {
      setDraftRevision(next.revision)
    }
    setContent(''); clientId.current = crypto.randomUUID()
    setMessage(kind === 'guidance' ? '建议已保存，等待你决定是否采纳。' : '已记下，可以随时接着学。')
  })

  const decide = (id: number, status: 'accepted' | 'dismissed') => act(async () => {
    const next = await decideGuidance(id, status)
    if (context && JSON.stringify(next.profile) === JSON.stringify(context.profile)) {
      setDraftRevision(next.revision)
    }
    setContext(next)
    setMessage(status === 'accepted' ? '已采纳。需要调整当前关注时，可以展开下方设置。' : '已记为暂不采用。')
  })

  const copy = () => act(async () => {
    const { markdown } = await exportContext()
    try {
      await navigator.clipboard.writeText(markdown)
      setCopyText('')
      setMessage('共享上下文已复制，可以粘贴给 AI。')
    } catch {
      setCopyText(markdown)
      setMessage('请从下方文本框选择并复制共享上下文。')
    }
  })

  if (!context || !draft) return <div className="page">
    {error ? <><p role="alert">{error}</p><button onClick={() => void load()}>重新加载</button></>
      : <p><Loader2 className="spin" size={18} /> 正在读取学习近况…</p>}
  </div>

  const p = context.profile
  const lastProgress = context.entries.find((e) => e.kind === 'progress')
  const visibleEntries = allEntries ? context.entries : context.entries.slice(0, 5)
  const patch = (next: Partial<LearningProfile>) => setDraft({ ...draft, ...next })

  return <div className="page study-home">
    <header className="page-head">
      <div><p className="eyebrow">{context.today} · 学习与交流</p><h1>从这里继续</h1></div>
      <div className="home-actions">
        <button className="text-button" disabled={busy} onClick={refresh}><RefreshCw size={16} /> 刷新近况</button>
        <button className="text-button" disabled={busy} onClick={copy}><Copy size={16} /> 复制给 AI</button>
      </div>
    </header>
    {error && <div className="home-error" role="alert">{error} <button disabled={busy} onClick={() => void act(load)}>重新加载共享信息</button><p>重新加载前，请复制尚未保存的草稿。</p></div>}
    {message && <div className="toast" role="status">{message}</div>}
    {context.export_pending && <div className="home-notice" role="status">
      {context.export_error || '数据库记录已保存，共享文件等待更新。'}
      <button disabled={busy} onClick={() => void act(async () => { setContext(await retryContextExport()) })}><RefreshCw size={14} /> 重试更新共享文件</button>
    </div>}

    <section className="card focus-card">
      <p className="eyebrow">{p.phase || '阶段由你决定'}</p>
      <h2>{p.focus || '选择一个现在感兴趣的主题'}</h2>
      {p.mode === 'paused' ? <p>当前暂停中。想继续时，再调整节奏即可。</p>
        : <p className="focus-next">{p.next_step || '接续点还没有填写。可以直接打开文档，也可以留一句近况。'}</p>}
      <div className="home-actions">
        <button className="primary-button" onClick={() => onDocument(p.document_path || undefined)}><BookOpen size={16} /> {p.document_path ? '继续关联文档' : '打开文档'}</button>
        <a className="text-button" href="#shared-note"><MessageCircle size={16} /> 留一句近况或问题</a>
      </div>
      {lastProgress && <details className="home-details"><summary>上次记录 · {lastProgress.date}</summary><Markdown text={lastProgress.content} /></details>}
    </section>

    <section className="card" id="shared-note">
      <h3>与 AI 共享近况</h3>
      <p className="card-sub">进展、疑问和想法都可以记在这里，留空也可以继续学习。AI 建议由你决定是否采纳。</p>
      <form onSubmit={(e) => { e.preventDefault(); void record() }}>
        <label className="home-label">这次想记什么
          <select disabled={busy} value={kind} onChange={(e) => { setKind(e.target.value as LearningEntry['kind']); clientId.current = crypto.randomUUID() }}>
            <option value="progress">学习进展</option><option value="question">想问 AI</option><option value="guidance">转入 AI 的建议</option>
          </select>
        </label>
        <textarea disabled={busy} aria-label="学习近况或问题" rows={3} maxLength={6000} value={content}
          onChange={(e) => { setContent(e.target.value); clientId.current = crypto.randomUUID() }}
          placeholder={kind === 'question' ? '例如：压缩这一部分能讲清了，接下来应该补哪块基础？' : '例如：今天整理了字典压缩，收益能解释，更新路径还想再看看。'} />
        <div className="home-actions"><button className="primary-button" type="submit" disabled={busy || !content.trim()}><Save size={16} /> 保存这条记录</button>
          <span className="home-muted">问题会进入共享上下文，供 AI 后续读取。</span></div>
      </form>
      {copyText && <label className="home-label">可复制的共享上下文<textarea readOnly rows={8} value={copyText} onFocus={(e) => e.target.select()} /></label>}
    </section>

    <details className="card home-details">
      <summary>调整当前关注与学习偏好</summary>
      <form onSubmit={(e) => { e.preventDefault(); void saveProfile() }}>
        <fieldset className="profile-form" disabled={busy}>
        <label>当前阶段<input maxLength={120} value={draft.phase} onChange={(e) => patch({ phase: e.target.value })} /></label>
        <label>关注主题<input maxLength={250} value={draft.focus} onChange={(e) => patch({ focus: e.target.value })} /></label>
        <label className="wide">留给下次的接续点<textarea rows={2} maxLength={2000} value={draft.next_step} onChange={(e) => patch({ next_step: e.target.value })} /></label>
        <label className="wide">近期目标<textarea rows={2} maxLength={1000} value={draft.goal} onChange={(e) => patch({ goal: e.target.value })} /></label>
        <label className="wide">希望 AI 怎样帮助你<textarea rows={3} maxLength={3000} value={draft.preferences} onChange={(e) => patch({ preferences: e.target.value })} /></label>
        <label className="wide">暂缓主题（每行一个）<textarea rows={3} value={draft.paused_topics.join('\n')} onChange={(e) => patch({ paused_topics: e.target.value.split('\n') })} /></label>
        <label>关联已有文档<select value={draft.document_path} onChange={(e) => patch({ document_path: e.target.value })}>
          <option value="">暂不关联</option>
          {draft.document_path && !docOptions.some((d) => d.path === draft.document_path) && <option value={draft.document_path}>{draft.document_path}（待确认）</option>}
          {docOptions.map((d) => <option key={d.path} value={d.path}>{d.name}</option>)}
        </select>{docError && <small>{docError}</small>}</label>
        <label>学习节奏<select value={draft.mode} onChange={(e) => patch({ mode: e.target.value as LearningProfile['mode'] })}><option value="active">按需学习</option><option value="paused">暂停，之后自己恢复</option></select></label>
        <div className="home-actions wide"><button className="primary-button" type="submit" disabled={busy}>保存当前关注</button></div>
        </fieldset>
      </form>
    </details>

    <section className="card">
      <h3>最近交流</h3>
      {!visibleEntries.length && <p className="home-muted">还没有记录。之后有想保留的进展或问题，再记下来。</p>}
      <div className="shared-feed">{visibleEntries.map((e) => <article key={e.id} className={`shared-entry ${e.kind}`}>
        <div className="shared-meta"><strong>{KIND_LABEL[e.kind]}</strong><span>{e.date} · {e.author === 'user' ? '你' : 'AI'}</span>{e.kind === 'guidance' && <span>{STATUS_LABEL[e.status]}</span>}</div>
        <Markdown text={e.content} />
        {e.kind === 'guidance' && e.status === 'proposed' && <div className="home-actions"><button disabled={busy} onClick={() => void decide(e.id, 'accepted')}>采纳</button><button disabled={busy} onClick={() => void decide(e.id, 'dismissed')}>暂不采用</button></div>}
      </article>)}</div>
      {context.entries.length > 5 && <button className="text-button" onClick={() => setAllEntries(!allEntries)}>{allEntries ? '收起' : `查看最近 ${context.entries.length} 条`}</button>}
    </section>

    <details className="card home-details">
      <summary>按日期查看历史日报</summary>
      <form className="home-actions" onSubmit={(e) => { e.preventDefault(); void act(async () => { setHistory(await fetchToday(historyDate)) }) }}>
        <input aria-label="历史日报日期" type="date" required value={historyDate} onChange={(e) => setHistoryDate(e.target.value)} />
        <button type="submit" disabled={busy}>查看</button>
      </form>
      {history && <div><p className="home-muted">{history.date} · {history.exists ? '历史内容仅供参考，不结转为当前任务。' : '这一天没有日报，可以继续使用学习与交流。'}</p>
        {history.exists && <><Markdown text={history.summary} /><Markdown text={history.plan_raw} /><Markdown text={history.tomorrow} /></>}
      </div>}
    </details>
  </div>
}
