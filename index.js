export default {
  async fetch(request, env) {
    const auth = request.headers.get('x-worker-auth')
    if (!auth || auth !== env.WORKER_AUTH) return new Response('Unauthorized', { status: 401 })

    const url = new URL(request.url)
    const target = 'https://api.clashofclans.com' + url.pathname + url.search

    const headers = new Headers(request.headers)
    headers.set('Authorization', `Bearer ${env.COC_API_TOKEN}`)
    headers.set('Accept', 'application/json')
    headers.delete('x-worker-auth')

    const resp = await fetch(target, {
      method: request.method,
      headers,
      body: request.method === 'GET' || request.method === 'HEAD' ? null : request.body
    })
    return resp
  }
}
