export type Difficulty = '基础' | '中等' | '进阶'
export type ProblemKind = 'sql' | 'python' | 'quiz' | 'case'

export interface Lesson {
  id: string
  title: string
  duration: number
  summary: string
  objectives: string[]
  content: Array<{
    heading: string
    body: string
    code?: string
  }>
  checkpoint: string[]
}

export interface Module {
  id: string
  week: string
  title: string
  kicker: string
  color: string
  lessons: Lesson[]
}

export interface SqlProblem {
  id: string
  kind: 'sql'
  title: string
  difficulty: Difficulty
  tags: string[]
  company: string
  description: string
  requirements: string[]
  schema: string
  setupSql: string
  starterCode: string
  solution: string
  explanation: string
  hints: string[]
  orderSensitive?: boolean
}

export interface PythonProblem {
  id: string
  kind: 'python'
  title: string
  difficulty: Difficulty
  tags: string[]
  company: string
  description: string
  requirements: string[]
  schema: string
  starterCode: string
  testCode: string
  solution: string
  explanation: string
  hints: string[]
}

export interface QuizProblem {
  id: string
  kind: 'quiz'
  title: string
  difficulty: Difficulty
  tags: string[]
  company: string
  description: string
  requirements: string[]
  schema: string
  options: string[]
  correctIndex: number
  solution: string
  explanation: string
  hints: string[]
}

export interface CaseProblem {
  id: string
  kind: 'case'
  title: string
  difficulty: Difficulty
  tags: string[]
  company: string
  description: string
  requirements: string[]
  schema: string
  rubric: string[]
  solution: string
  explanation: string
  hints: string[]
}

export type Problem = SqlProblem | PythonProblem | QuizProblem | CaseProblem

export interface ProgressState {
  completedLessons: string[]
  solvedProblems: string[]
  attempts: Record<string, number>
  bookmarks: string[]
  notes: Record<string, string>
  streak: number
  lastStudyDate?: string
}
