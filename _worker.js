/**
 * ☢️ CLOUDFLARE PAGES UNIVERSAL EDGE WORKER (_worker.js)
 * Makes all API endpoints 100% PERMANENT under https://phone-whisper-server.pages.dev
 * Automatically routes all /v1/*, /inference, /telemetry, /tts to the live phone tunnel.
 */

const GITHUB_ENDPOINT_URL = "https://raw.githubusercontent.com/Electroiscoding/phone-whisper-server/main/endpoint.json";
const SHARED_SECRET = "mobile_ai_nuclear_key";

let cachedOrigin = "https://investment-nine-cumulative-nothing.trycloudflare.com";
let lastFetchTime = Date.now();
const CACHE_TTL_MS = 10000; // 10 seconds

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, HEAD",
  "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With, Accept, Origin, Cache-Control, X-Accel-Buffering, x-api-key, *",
  "Access-Control-Expose-Headers": "*",
  "Access-Control-Max-Age": "86400"
};

async function getLiveOrigin(forceRefresh = false) {
  const now = Date.now();
  if (!forceRefresh && cachedOrigin && (now - lastFetchTime < CACHE_TTL_MS)) {
    return cachedOrigin;
  }

  // 1. Primary: 100% Uncached GitHub REST API with raw header (Bypasses raw CDN 5-minute cache)
  try {
    const apiRes = await fetch(`https://api.github.com/repos/Electroiscoding/phone-whisper-server/contents/endpoint.json?ref=main&_t=${now}`, {
      headers: {
        "User-Agent": "Cloudflare-Pages-Worker/3.0",
        "Accept": "application/vnd.github.v3.raw",
        "Cache-Control": "no-cache"
      }
    });
    if (apiRes.ok) {
      const data = await apiRes.json();
      if (data && data.endpoint && data.endpoint.startsWith("https://")) {
        cachedOrigin = data.endpoint.replace(/\/+$/, "");
        lastFetchTime = now;
        return cachedOrigin;
      }
    }
  } catch (err) {}

  // 2. Secondary Fallback: Raw GitHub CDN
  try {
    const res = await fetch(`${GITHUB_ENDPOINT_URL}?_t=${now}`, {
      headers: { "User-Agent": "Cloudflare-Pages-Worker/3.0", "Cache-Control": "no-cache" },
      cf: { cacheTtl: 0, cacheEverything: false }
    });
    if (res.ok) {
      const data = await res.json();
      if (data && data.endpoint && data.endpoint.startsWith("https://")) {
        cachedOrigin = data.endpoint.replace(/\/+$/, "");
        lastFetchTime = now;
        return cachedOrigin;
      }
    }
  } catch (err) {}

  return cachedOrigin;
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // 1. Universal CORS Pre-flight
    if (request.method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: CORS_HEADERS
      });
    }

    // Determine if this is an API route or static asset
    const apiPrefixes = ["/v1/", "/auth/", "/s/"];
    const apiExactPaths = ["/inference", "/telemetry", "/tts", "/speech", "/health", "/models", "/backends", "/register_tunnel"];
    const isApi = apiPrefixes.some(prefix => url.pathname.startsWith(prefix)) || apiExactPaths.includes(url.pathname);

    // If it's a static frontend request, serve through Cloudflare Pages static assets
    if (url.pathname === "/dashboard" && env.ASSETS) {
      const newUrl = new URL(request.url);
      newUrl.pathname = "/dashboard.html";
      return env.ASSETS.fetch(new Request(newUrl, request));
    }

    if (!isApi && env.ASSETS) {
      return env.ASSETS.fetch(request);
    }

    // 2. Direct Tunnel Registration from Phone
    if (url.pathname === "/register_tunnel" && request.method === "POST") {
      try {
        const body = await request.json();
        if (body.endpoint && body.secret === SHARED_SECRET) {
          cachedOrigin = body.endpoint.replace(/\/+$/, "");
          lastFetchTime = Date.now();
          return new Response(JSON.stringify({ status: "registered", active_origin: cachedOrigin }), {
            headers: { ...CORS_HEADERS, "Content-Type": "application/json" }
          });
        }
      } catch (err) {
        return new Response(JSON.stringify({ error: err.message }), {
          status: 400,
          headers: { ...CORS_HEADERS, "Content-Type": "application/json" }
        });
      }
    }

    // 3. Resilient Proxy Request to Live Phone Origin with Autonomous Multi-Attempt Retry
    let origin = await getLiveOrigin(false);
    let targetUrl = `${origin}${url.pathname}${url.search}`;

    let response = null;
    let attempt = 0;
    const maxAttempts = 3;

    while (attempt < maxAttempts) {
      attempt++;
      try {
        const proxyReq = new Request(targetUrl, {
          method: request.method,
          headers: request.headers,
          body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
          redirect: "follow"
        });

        response = await fetch(proxyReq);

        // If origin returned 502, 503, 504, 530, force-refresh endpoint from GitHub and retry
        if ([502, 503, 504, 530].includes(response.status) && attempt < maxAttempts) {
          await new Promise(r => setTimeout(r, attempt * 300));
          origin = await getLiveOrigin(true);
          targetUrl = `${origin}${url.pathname}${url.search}`;
          continue;
        }

        break;
      } catch (fetchErr) {
        if (attempt < maxAttempts) {
          await new Promise(r => setTimeout(r, attempt * 400));
          origin = await getLiveOrigin(true);
          targetUrl = `${origin}${url.pathname}${url.search}`;
          continue;
        }
      }
    }

    // 4. Fallback if Phone is Reconnecting
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

    // 5. Return Phone's Response with CORS headers attached
    const responseHeaders = new Headers(response.headers);
    Object.entries(CORS_HEADERS).forEach(([k, v]) => responseHeaders.set(k, v));

    return new Response(request.method === "HEAD" ? null : response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders
    });
  }
};
