/**
 * SHARED PAGES FUNCTIONS PROXY UTILITY (functions/_proxy.js)
 * Automatically discovers live phone datacenter tunnel and reverse proxies requests.
 */

const GITHUB_ENDPOINT_URL = "https://raw.githubusercontent.com/Electroiscoding/phone-whisper-server/main/endpoint.json";
const JSDELIVR_ENDPOINT_URL = "https://cdn.jsdelivr.net/gh/Electroiscoding/phone-whisper-server@main/endpoint.json";

let cachedOrigin = null;
let lastFetchTime = 0;
const CACHE_TTL_MS = 30000;

export function setLiveOrigin(newOrigin) {
  if (newOrigin && newOrigin.startsWith("https://")) {
    cachedOrigin = newOrigin.replace(/\/+$/, "");
    lastFetchTime = Date.now();
  }
}

export const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, HEAD, PATCH",
  "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With, Accept, Origin, Cache-Control, X-Accel-Buffering, x-api-key, Range, *",
  "Access-Control-Expose-Headers": "*",
  "Access-Control-Max-Age": "86400"
};

async function fetchWithTimeout(url, options = {}, timeoutMs = 3000) {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { ...options, signal: controller.signal });
    clearTimeout(id);
    return res;
  } catch (err) {
    clearTimeout(id);
    throw err;
  }
}

export async function getLiveOrigin(forceRefresh = false) {
  const now = Date.now();
  if (!forceRefresh && cachedOrigin && (now - lastFetchTime < CACHE_TTL_MS)) {
    return cachedOrigin;
  }

  // 1. Primary: Raw GitHub
  try {
    const res = await fetchWithTimeout(`${GITHUB_ENDPOINT_URL}?_t=${now}`, {
      headers: { "User-Agent": "Cloudflare-Pages-Functions/3.0", "Cache-Control": "no-cache, no-store, must-revalidate" }
    }, 2000);
    if (res.ok) {
      const data = await res.json();
      if (data && data.endpoint && data.endpoint.startsWith("https://")) {
        cachedOrigin = data.endpoint.replace(/\/+$/, "");
        lastFetchTime = now;
        return cachedOrigin;
      }
    }
  } catch (err) {}

  // 2. Secondary: jsDelivr Edge CDN
  try {
    const jsdelivrRes = await fetchWithTimeout(`${JSDELIVR_ENDPOINT_URL}?_t=${now}`, {
      headers: { "Cache-Control": "no-cache, no-store" }
    }, 2000);
    if (jsdelivrRes.ok) {
      const data = await jsdelivrRes.json();
      if (data && data.endpoint && data.endpoint.startsWith("https://")) {
        cachedOrigin = data.endpoint.replace(/\/+$/, "");
        lastFetchTime = now;
        return cachedOrigin;
      }
    }
  } catch (err) {}

  return cachedOrigin || "";
}

export async function handleOptions(context) {
  return new Response(null, {
    status: 204,
    headers: CORS_HEADERS
  });
}

export async function handleRequest(context) {
  const { request } = context;

  if (request.method === "OPTIONS") {
    return handleOptions(context);
  }

  const url = new URL(request.url);
  let origin = await getLiveOrigin(false);
  let targetUrl = `${origin}${url.pathname}${url.search}`;

  let reqBody = undefined;
  if (!["GET", "HEAD"].includes(request.method)) {
    try {
      reqBody = await request.arrayBuffer();
    } catch (e) {
      reqBody = request.body;
    }
  }

  let response = null;
  let attempt = 0;
  const maxAttempts = 3;
  const isLongRunning = url.pathname.includes("/speech") || 
                        url.pathname.includes("/transcriptions") || 
                        url.pathname.includes("/chat") || 
                        url.pathname.includes("/inference") ||
                        url.pathname.includes("/storage") ||
                        url.pathname.startsWith("/s/");
  const timeoutMs = isLongRunning ? 60000 : 15000;

  while (attempt < maxAttempts) {
    attempt++;
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

      const proxyHeaders = new Headers(request.headers);
      proxyHeaders.delete("cf-connecting-ip");
      proxyHeaders.delete("cf-ray");
      proxyHeaders.delete("cf-ipcountry");
      proxyHeaders.delete("cf-visitor");
      try {
        const targetHost = new URL(targetUrl).host;
        proxyHeaders.set("Host", targetHost);
      } catch (e) {}

      const proxyReq = new Request(targetUrl, {
        method: request.method,
        headers: proxyHeaders,
        body: reqBody instanceof ArrayBuffer ? reqBody.slice(0) : reqBody,
        redirect: "follow",
        signal: controller.signal
      });

      response = await fetch(proxyReq);
      clearTimeout(timeoutId);

      // Invalidate cache and retry on bad gateway / tunnel restart codes
      if ([403, 502, 503, 504, 530].includes(response.status) && attempt < maxAttempts) {
        cachedOrigin = null;
        await new Promise(r => setTimeout(r, attempt * 250));
        origin = await getLiveOrigin(true);
        targetUrl = `${origin}${url.pathname}${url.search}`;
        continue;
      }

      break;
    } catch (fetchErr) {
      if (attempt < maxAttempts) {
        cachedOrigin = null;
        await new Promise(r => setTimeout(r, attempt * 300));
        origin = await getLiveOrigin(true);
        targetUrl = `${origin}${url.pathname}${url.search}`;
        continue;
      }
    }
  }

  if (!response || [502, 503, 504, 530].includes(response.status)) {
    const errorBody = JSON.stringify({
      status: "reconnecting",
      error: "Phone AI Datacenter is self-healing / refreshing tunnel.",
      cached_origin: origin,
      retry_after_sec: 2,
      timestamp: Math.floor(Date.now() / 1000)
    });

    return new Response(errorBody, {
      status: 503,
      headers: {
        ...CORS_HEADERS,
        "Content-Type": "application/json",
        "Retry-After": "2"
      }
    });
  }

  const responseHeaders = new Headers(response.headers);
  Object.entries(CORS_HEADERS).forEach(([k, v]) => responseHeaders.set(k, v));

  return new Response(request.method === "HEAD" ? null : response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: responseHeaders
  });
}
