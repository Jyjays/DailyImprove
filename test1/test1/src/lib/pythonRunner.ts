export interface PythonRunResult {
  output: string
  error?: string
  elapsed: number
}

const workerSource = `
let pyodideReady;
self.onmessage = async (event) => {
  const { code, testCode } = event.data;
  const started = performance.now();
  try {
    if (!pyodideReady) {
      self.postMessage({ type: 'progress', stage: 'loading-script', elapsed: performance.now() - started });
      importScripts('https://cdn.jsdelivr.net/pyodide/v0.28.3/full/pyodide.js');
      self.postMessage({ type: 'progress', stage: 'loading-runtime', elapsed: performance.now() - started });
      pyodideReady = loadPyodide({ indexURL: 'https://cdn.jsdelivr.net/pyodide/v0.28.3/full/' });
    }
    const pyodide = await pyodideReady;
    self.postMessage({ type: 'progress', stage: 'loading-packages', elapsed: performance.now() - started });
    await pyodide.loadPackage(['pandas', 'numpy']);
    self.postMessage({ type: 'progress', stage: 'running-code', elapsed: performance.now() - started });
    pyodide.runPython(\`import sys, io\n_codex_stdout = io.StringIO()\nsys.stdout = _codex_stdout\n\`);
    await pyodide.runPythonAsync(code + '\\n\\n' + testCode);
    const output = pyodide.runPython('_codex_stdout.getvalue()');
    pyodide.runPython('sys.stdout = sys.__stdout__');
    self.postMessage({ output, elapsed: performance.now() - started });
  } catch (error) {
    try { const pyodide = await pyodideReady; pyodide.runPython('sys.stdout = sys.__stdout__'); } catch {}
    self.postMessage({ output: '', error: String(error), elapsed: performance.now() - started });
  }
};`

let worker: Worker | null = null

function getWorker() {
  if (!worker) {
    const blob = new Blob([workerSource], { type: 'application/javascript' })
    worker = new Worker(URL.createObjectURL(blob))
  }
  return worker
}

export function runPython(code: string, testCode: string, timeoutMs = 60000, onProgress?: (stage: string) => void): Promise<PythonRunResult> {
  return new Promise((resolve) => {
    const activeWorker = getWorker()
    const timeout = window.setTimeout(() => {
      activeWorker.terminate()
      worker = null
      resolve({ output: '', error: '运行超时：程序已在60秒后终止。请检查网络、死循环或过慢操作。', elapsed: timeoutMs })
    }, timeoutMs)

    activeWorker.onmessage = (event: MessageEvent<PythonRunResult & { type?: string, stage?: string }>) => {
      if (event.data.type === 'progress') {
        console.info(`[python-runner] ${event.data.stage} (${Math.round(event.data.elapsed)} ms)`)
        onProgress?.(event.data.stage ?? '')
        return
      }
      window.clearTimeout(timeout)
      resolve(event.data)
    }
    activeWorker.postMessage({ code, testCode })
  })
}
