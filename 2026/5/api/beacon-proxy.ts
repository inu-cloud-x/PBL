export const config = { runtime: 'edge' }

// @ts-ignore — process.env is available in Vercel Edge Runtime
const TARGET = (typeof process !== 'undefined' && process.env.VITE_CONSENSUS_RPC_URL)
  ? process.env.VITE_CONSENSUS_RPC_URL
  : 'https://ethereum-sepolia-beacon-api.publicnode.com'

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, OPTIONS',
  'Access-Control-Allow-Headers': 'Accept, Content-Type',
}

export default async function handler(request: Request): Promise<Response> {
  if (request.method === 'OPTIONS') {
    return new Response(null, { status: 204, headers: CORS_HEADERS })
  }

  const url = new URL(request.url)
  const beaconPath = url.pathname.replace(/^\/api\/beacon-proxy\/?/, '/') || '/'
  const target = `${TARGET}${beaconPath}${url.search}`

  const upstream = await fetch(target, {
    method: request.method,
    headers: { Accept: request.headers.get('Accept') ?? 'application/json' },
  })

  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      'Content-Type': upstream.headers.get('Content-Type') ?? 'application/json',
      ...CORS_HEADERS,
    },
  })
}
