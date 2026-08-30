/**
 * ☢️ NUCLEAR CLOUDFLARE EDGE WORKER
 * Self-Healing Dynamic Failover & Universal Reverse Proxy for Phone AI Datacenter
 */

const GITHUB_ENDPOINT_URL = "https://raw.githubusercontent.com/Electroiscoding/phone-whisper-server/main/endpoint.json";

// In-Memory Edge Cache for Active Tunnel Target
let cachedOrigin = null;
let lastFetchTime = 0;
const CACHE_TTL_MS = 10000; // 10 seconds

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, HEAD",
  "Access-Control-Allow-Headers": "*",
  "Access-Control-Expose-Headers": "*",
  "Access-Control-Max-Age": "86400"
};

async function getLiveOrigin(forceRefresh = false) {
  const now = Date.now();
  if (!forceRefresh && cachedOrigin && (now - lastFetchTime < CACHE_TTL_MS)) {
    return cachedOrigin;
  }

  try {
    const res = await fetch(`${GITHUB_ENDPOINT_URL}?_t=${now}`, {
      headers: { "User-Agent": "Cloudflare-Edge-Worker/2.0" },
      cf: { cacheTtl: 0, cacheEverything: false }
    });
    if (res.ok) {
      const data = await res.json();
      if (data.endpoint && data.endpoint.startsWith("https://")) {
        cachedOrigin = data.endpoint.replace(/\/+$/, "");
        lastFetchTime = now;
        return cachedOrigin;
      }
    }
  } catch (err) {
    console.error("Failed to fetch fresh endpoint.json:", err);
  }

  return cachedOrigin || "https://distributors-civil-patent-contributing.trycloudflare.com";
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

    // 2. Fetch Origin with Auto-Retry & Nuclear Failover
    let origin = await getLiveOrigin(false);
    let targetUrl = `${origin}${url.pathname}${url.search}`;

    let response = null;
    let attempt = 0;

    while (attempt < 2) {
      attempt++;
      try {
        const proxyReq = new Request(targetUrl, {
          method: request.method,
          headers: request.headers,
          body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
          redirect: "follow"
        });

        response = await fetch(proxyReq);

        // If origin returned 502, 530, or 504, try fresh endpoint from GitHub
        if ([502, 503, 504, 530].includes(response.status) && attempt === 1) {
          console.warn(`Origin returned ${response.status}. Fetching latest tunnel from GitHub...`);
          origin = await getLiveOrigin(true);
          targetUrl = `${origin}${url.pathname}${url.search}`;
          continue;
        }

        // Successfully received valid response from phone
        break;
      } catch (fetchErr) {
        console.error(`Fetch attempt ${attempt} failed:`, fetchErr);
        if (attempt === 1) {
          origin = await getLiveOrigin(true);
          targetUrl = `${origin}${url.pathname}${url.search}`;
          continue;
        }
      }
    }

    // 3. If phone is genuinely unreachable, return structured JSON with CORS
    if (!response || [502, 503, 504, 530].includes(response.status)) {
      const errorBody = JSON.stringify({
        status: "reconnecting",
        error: "Phone AI Gateway is self-healing / reconnecting tunnel.",
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

    // 4. Attach Full CORS Headers to Phone Response
    const responseHeaders = new Headers(response.headers);
    Object.entries(CORS_HEADERS).forEach(([k, v]) => responseHeaders.set(k, v));

    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders
    });
  }
};
