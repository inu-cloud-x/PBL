import { wrap, type Remote } from 'comlink'
import { createPublicClient, custom } from 'viem'
import { getChain, getConfig } from '../config'

export type HeliosStatus = 'idle' | 'initializing' | 'ready' | 'failed'

type WorkerApi = {
  init(executionRpc: string, consensusRpc: string): Promise<void>
  request(method: string, params?: unknown[]): Promise<unknown>
  dispose(): void
}

let workerProxy: Remote<WorkerApi> | null = null
let _worker: Worker | null = null
let _status: HeliosStatus = 'idle'
let _error: Error | null = null
let _initPromise: Promise<void> | null = null

export function heliosStatus(): HeliosStatus {
  return _status
}

export function heliosError(): Error | null {
  return _error
}

export function isOutOfSync(e: unknown): boolean {
  return e instanceof Error && (
    e.message.includes('out of sync') ||
    e.message.includes('maximum proof window')
  )
}

export function resetHelios(): void {
  workerProxy?.dispose()
  _worker?.terminate()
  _worker = null
  workerProxy = null
  _status = 'idle'
  _error = null
  _initPromise = null
}

export function initHelios(): Promise<void> {
  if (_initPromise) return _initPromise
  _initPromise = _doInit()
  return _initPromise
}

async function _doInit(): Promise<void> {
  const config = getConfig()
  if (!config.executionRpcUrl) throw new Error('VITE_EXECUTION_RPC_URL이 설정되지 않았습니다')

  _status = 'initializing'
  _error = null

  try {
    // Spawn a dedicated Web Worker — all WASM/crypto work runs off the main thread
    _worker = new Worker(
      new URL('../workers/helios.worker.ts', import.meta.url),
      { type: 'module' },
    )
    workerProxy = wrap<WorkerApi>(_worker)

    await workerProxy.init(
      config.executionRpcUrl,
      `${window.location.origin}/api/beacon-proxy`,
    )

    _status = 'ready'
  } catch (e) {
    _error = e instanceof Error ? e : new Error(String(e))
    _status = 'failed'
    _initPromise = null
    _worker?.terminate()
    _worker = null
    workerProxy = null
    throw _error
  }
}

export function createHeliosClient() {
  if (!workerProxy || _status !== 'ready') {
    throw new Error('Helios가 아직 동기화되지 않았습니다')
  }

  // Proxy all viem RPC calls through the Worker
  return createPublicClient({
    chain: getChain(),
    transport: custom({
      request: ({ method, params }) =>
        workerProxy!.request(method, params as unknown[]),
    }),
  })
}
