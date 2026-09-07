import * as duckdb from '@duckdb/duckdb-wasm'

type QueryRow = Record<string, unknown>

let dbPromise: Promise<duckdb.AsyncDuckDB> | null = null

async function createDatabase() {
  const bundles = duckdb.getJsDelivrBundles()
  const bundle = await duckdb.selectBundle(bundles)
  // Browsers disallow constructing a Worker directly from a cross-origin CDN URL.
  // A same-origin Blob worker can import the published DuckDB worker safely.
  const workerUrl = URL.createObjectURL(new Blob([
    `importScripts(${JSON.stringify(bundle.mainWorker)});`,
  ], { type: 'text/javascript' }))
  const worker = new Worker(workerUrl)
  const logger = new duckdb.ConsoleLogger(duckdb.LogLevel.WARNING)
  const db = new duckdb.AsyncDuckDB(logger, worker)
  await db.instantiate(bundle.mainModule, bundle.pthreadWorker)
  URL.revokeObjectURL(workerUrl)
  return db
}

function getDatabase() {
  if (!dbPromise) dbPromise = createDatabase()
  return dbPromise
}

function serializeValue(value: unknown): unknown {
  if (typeof value === 'bigint') return Number(value)
  if (value instanceof Date) return value.toISOString().replace('T', ' ').replace('.000Z', '')
  if (value && typeof value === 'object' && 'toString' in value) return String(value)
  return value
}

function tableToRows(table: Awaited<ReturnType<duckdb.AsyncDuckDBConnection['query']>>): QueryRow[] {
  return table.toArray().map((row) => {
    const json = row.toJSON() as QueryRow
    return Object.fromEntries(Object.entries(json).map(([key, value]) => [key, serializeValue(value)]))
  })
}

function canonical(rows: QueryRow[], orderSensitive = false) {
  const normalized = rows.map((row) => Object.fromEntries(
    Object.entries(row).map(([key, value]) => [key.toLowerCase(), value === null ? null : String(value)]),
  ))
  if (!orderSensitive) normalized.sort((a, b) => JSON.stringify(a).localeCompare(JSON.stringify(b)))
  return normalized
}

export interface SqlRunResult {
  rows: QueryRow[]
  columns: string[]
  passed?: boolean
  expected?: QueryRow[]
  elapsed: number
}

export async function runSql(setupSql: string, userSql: string, solution?: string, orderSensitive = false): Promise<SqlRunResult> {
  const started = performance.now()
  const db = await getDatabase()
  const conn = await db.connect()
  try {
    await conn.query(setupSql)
    const result = await conn.query(userSql)
    const rows = tableToRows(result)
    const columns = result.schema.fields.map((field) => field.name)
    if (!solution) return { rows, columns, elapsed: performance.now() - started }

    const expectedTable = await conn.query(solution)
    const expected = tableToRows(expectedTable)
    const expectedColumns = expectedTable.schema.fields.map((field) => field.name.toLowerCase())
    const actualColumns = columns.map((column) => column.toLowerCase())
    const passed = JSON.stringify(actualColumns) === JSON.stringify(expectedColumns)
      && JSON.stringify(canonical(rows, orderSensitive)) === JSON.stringify(canonical(expected, orderSensitive))

    return { rows, columns, expected, passed, elapsed: performance.now() - started }
  } finally {
    await conn.close()
  }
}
