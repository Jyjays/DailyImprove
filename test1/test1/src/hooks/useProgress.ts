import { useCallback, useEffect, useState } from 'react'
import type { ProgressState } from '../types'

const STORAGE_KEY = 'data-analyst-academy-progress-v1'
const initialState: ProgressState = {
  completedLessons: [], solvedProblems: [], attempts: {}, bookmarks: [], notes: {}, streak: 0,
}

export function useProgress() {
  const [progress, setProgress] = useState<ProgressState>(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY)
      return stored ? { ...initialState, ...JSON.parse(stored) } : initialState
    } catch { return initialState }
  })

  useEffect(() => { localStorage.setItem(STORAGE_KEY, JSON.stringify(progress)) }, [progress])

  const recordStudy = useCallback(() => {
    const today = new Date().toISOString().slice(0, 10)
    setProgress((current) => {
      if (current.lastStudyDate === today) return current
      const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10)
      return { ...current, streak: current.lastStudyDate === yesterday ? current.streak + 1 : 1, lastStudyDate: today }
    })
  }, [])

  const toggleLesson = useCallback((id: string) => {
    recordStudy()
    setProgress((current) => ({ ...current, completedLessons: current.completedLessons.includes(id) ? current.completedLessons.filter((item) => item !== id) : [...current.completedLessons, id] }))
  }, [recordStudy])

  const recordAttempt = useCallback((id: string, passed: boolean) => {
    recordStudy()
    setProgress((current) => ({
      ...current,
      attempts: { ...current.attempts, [id]: (current.attempts[id] ?? 0) + 1 },
      solvedProblems: passed && !current.solvedProblems.includes(id) ? [...current.solvedProblems, id] : current.solvedProblems,
    }))
  }, [recordStudy])

  const toggleBookmark = useCallback((id: string) => setProgress((current) => ({ ...current, bookmarks: current.bookmarks.includes(id) ? current.bookmarks.filter((item) => item !== id) : [...current.bookmarks, id] })), [])
  const saveNote = useCallback((id: string, note: string) => setProgress((current) => ({ ...current, notes: { ...current.notes, [id]: note } })), [])

  return { progress, toggleLesson, recordAttempt, toggleBookmark, saveNote }
}
