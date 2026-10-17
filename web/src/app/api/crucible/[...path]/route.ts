// Server-side proxy to the Crucible API: the API key stays on the server and SSE streams pass through untouched.
const API_URL = process.env.CRUCIBLE_API_URL ?? "http://127.0.0.1:8765";
const API_KEY = process.env.CRUCIBLE_API_KEY ?? "";

async function forward(request: Request, ctx: RouteContext<"/api/crucible/[...path]">): Promise<Response> {
  const { path } = await ctx.params;
  const incoming = new URL(request.url);
  const target = `${API_URL}/v1/${path.map(encodeURIComponent).join("/")}${incoming.search}`;
  const headers = new Headers({ accept: request.headers.get("accept") ?? "application/json" });
  if (API_KEY) headers.set("x-api-key", API_KEY);
  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  if (hasBody) headers.set("content-type", "application/json");
  const upstream = await fetch(target, {
    method: request.method,
    headers,
    body: hasBody ? await request.text() : undefined,
    cache: "no-store",
  });
  const responseHeaders = new Headers();
  for (const name of ["content-type", "cache-control"]) {
    const value = upstream.headers.get(name);
    if (value) responseHeaders.set(name, value);
  }
  return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
}

export const GET = forward;
export const POST = forward;
export const PUT = forward;
