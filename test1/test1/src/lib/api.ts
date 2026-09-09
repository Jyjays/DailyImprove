/** DailyImprove 后端接口封装。所有请求经 vite proxy 转发到 127.0.0.1:8000 */

export type CheckinStatus = 'done' | 'partial' | 'todo' | 'blocked'

export type KnowledgeKind = 'paper' | 'news' | 'blog'

export interface KnowledgeItem {
  id: number
  title: string
  url: string
  module: string
  kind: KnowledgeKind
  source_name: string
  /** 展示用日期：发布时间优先，没有则用入库时间 */
  date: string | null
  date_source: 'published' | 'fetched'
  is_favorite: boolean
  ai_summary: string
  origin_summary: string
  body_excerpt: string
  reason: string
  tags: string[]
  score: number | null
  final_score: number | null
  status: string
  author: string
  published_at: string | null
  fetched_at: string | null
  has_ai_summary: boolean
}

export interface KnowledgeResult {
  total: number
  page: number
  page_size: number
  total_pages: number
  days: number
  kind: string | null
  kind_counts: Record<string, number>
  favorite_count: number
  items: KnowledgeItem[]
}

export interface ChecklistRow {
  mark: string
  text: string
  status: CheckinStatus
}

export interface TodayPlan {
  date: string
  exists: boolean
  source_file: string | null
  commit: string
  summary: string
  plan: string[]
  plan_raw: string
  plan_table: { headers: string[]; rows: string[][] }
  checklist: ChecklistRow[]
  tomorrow: string
}

export interface CheckinRow {
  category: string
  title: string | null
  status: CheckinStatus
  note: string | null
  updated_at: string | null
}

export interface CourseItem {
  id: number
  title: string
  provider: string | null
  url: string | null
  description: string | null
  track: string
  phase: string | null
  resources: Array<{ name: string; url: string; type?: string }>
  status: string
  progress: number
}

const BASE = '/api/study'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    throw new Error(`接口错误 ${res.status}: ${path}`)
  }
  return res.json() as Promise<T>
}

/** 知识条目列表（分页） */
export function fetchKnowledge(params: {
  kind?: KnowledgeKind | 'all'
  days?: number          // 0 表示不限时间
  has_ai?: boolean
  favorite?: boolean
  q?: string
  module_key?: string
  page?: number
  page_size?: number
} = {}) {
  const qs = new URLSearchParams()
  if (params.kind && params.kind !== 'all') qs.set('kind', params.kind)
  if (params.days !== undefined) qs.set('days', String(params.days))
  if (params.has_ai) qs.set('has_ai', 'true')
  if (params.favorite) qs.set('favorite', 'true')
  if (params.q) qs.set('q', params.q)
  if (params.module_key) qs.set('module_key', params.module_key)
  if (params.page) qs.set('page', String(params.page))
  if (params.page_size) qs.set('page_size', String(params.page_size))
  return request<KnowledgeResult>(`/knowledge?${qs}`)
}

/** 收藏 / 取消收藏（切换），返回操作后的状态 */
export function toggleFavorite(id: number) {
  return request<{ id: number; favorited: boolean }>(`/knowledge/${id}/favorite`, {
    method: 'POST',
  })
}

/** 单条知识详情（含正文） */
export function fetchKnowledgeDetail(id: number) {
  return request<KnowledgeItem & { body: string }>(`/knowledge/${id}`)
}

/** 今日计划 */
export function fetchToday(date?: string) {
  const qs = date ? `?target_date=${date}` : ''
  return request<TodayPlan>(`/today${qs}`)
}

/** 读打卡 */
export function fetchCheckin(date?: string) {
  const qs = date ? `?date_str=${date}` : ''
  return request<{ date: string; items: CheckinRow[] }>(`/checkin${qs}`)
}

/** 存打卡（落库 + 回写 md） */
export function saveCheckin(date: string, items: Array<{
  category: string
  title?: string
  status: CheckinStatus
  note?: string
}>) {
  return request<{ ok: boolean; md_written: boolean; md_file: string | null }>('/checkin', {
    method: 'POST',
    body: JSON.stringify({ date, items }),
  })
}

/** 打卡统计 */
export function fetchCheckinStats(days = 30) {
  return request<{
    days: number
    by_category: Record<string, { done: number; total: number; rate: number }>
  }>(`/checkin/stats?days=${days}`)
}

/** 课程列表 */
export function fetchCourses(track?: string) {
  const qs = track ? `?track=${track}` : ''
  return request<{ total: number; items: CourseItem[] }>(`/courses${qs}`)
}

/** 新增课程 */
export function createCourse(payload: Omit<CourseItem, 'id'>) {
  return request<{ ok: boolean; id: number }>('/courses', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

/** 更新课程 */
export function updateCourse(id: number, payload: Omit<CourseItem, 'id'>) {
  return request<{ ok: boolean; id: number }>(`/courses/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

/** 删除课程 */
export function deleteCourse(id: number) {
  return request<{ ok: boolean }>(`/courses/${id}`, { method: 'DELETE' })
}

/** 打卡分类 -> 中文标签（与后端 CATEGORY_LABELS 保持一致） */
export const CATEGORY_LABELS: Record<string, string> = {
  'ai-infra': 'AI Infra',
  paper: '论文',
  interview: '面经',
  drone: '横向',
  blocker: '卡点',
}

export const STATUS_LABELS: Record<CheckinStatus, string> = {
  done: '已完成',
  partial: '部分完成',
  todo: '未做',
  blocked: '卡住',
}