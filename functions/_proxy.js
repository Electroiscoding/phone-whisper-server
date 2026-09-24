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

const B2_APP_KEY_ID = "0056b2f88b847c60000000003";
const B2_APP_KEY = "K005/3ZD3P9uF61mPNuuQjac1Yr0HMw";
const B2_BUCKET_ID = "866bf27f58e86b6894f70c16";
const B2_BUCKET_NAME = "netuark-storage";
const B2_DOWNLOAD_BASE = "https://f005.backblazeb2.com";

let cachedB2Token = null;
let b2TokenExpiry = 0;

async function getB2DownloadToken() {
  const now = Date.now();
  if (cachedB2Token && now < b2TokenExpiry) {
    return cachedB2Token;
  }
  try {
    const authHeader = "Basic " + btoa(B2_APP_KEY_ID + ":" + B2_APP_KEY);
    const authRes = await fetch("https://api.backblazeb2.com/b2api/v2/b2_authorize_account", {
      headers: { Authorization: authHeader }
    });
    if (!authRes.ok) return null;
    const authData = await authRes.json();
    const tokenRes = await fetch(authData.apiUrl + "/b2api/v2/b2_get_download_authorization", {
      method: "POST",
      headers: {
        Authorization: authData.authorizationToken,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        bucketId: B2_BUCKET_ID,
        fileNamePrefix: "",
        validDurationInSeconds: 86400
      })
    });
    if (!tokenRes.ok) return null;
    const tokenData = await tokenRes.json();
    cachedB2Token = tokenData.authorizationToken;
    b2TokenExpiry = now + (23 * 3600 * 1000);
    return cachedB2Token;
  } catch (e) {
    return null;
  }
}

export async function tryB2StorageFallback(request, url) {
  const isStorageReq = url.pathname.startsWith("/v1/storage/objects/") || url.pathname.startsWith("/s/");
  if (!isStorageReq || !["GET", "HEAD"].includes(request.method)) return null;

  let rawFileName = url.pathname.split("/").pop() || "";
  try { rawFileName = decodeURIComponent(rawFileName); } catch (e) {}
  if (!rawFileName || rawFileName.includes(".trashed")) return null;

  const token = await getB2DownloadToken();
  if (!token) return null;

  const subPath = url.pathname.replace(/^\/(v1\/storage\/objects|s)\//, "");
  const candidateKeys = [rawFileName];
  if (subPath && subPath !== rawFileName && !candidateKeys.includes(subPath)) {
    candidateKeys.push(subPath);
  }
  if (!rawFileName.startsWith("media/") && !candidateKeys.includes("media/" + rawFileName)) {
    candidateKeys.push("media/" + rawFileName);
  }

  const forwardHeaders = new Headers();
  if (request.headers.has("range")) {
    forwardHeaders.set("Range", request.headers.get("range"));
  }

  const ext = (rawFileName.split('.').pop() || '').toLowerCase();
  const MIME_MAP = {
    wav: 'audio/wav',
    webm: 'audio/webm',
    mp3: 'audio/mpeg',
    ogg: 'audio/ogg',
    m4a: 'audio/mp4',
    mp4: 'video/mp4',
    png: 'image/png',
    jpg: 'image/jpeg',
    jpeg: 'image/jpeg',
    webp: 'image/webp',
    gif: 'image/gif',
    svg: 'image/svg+xml'
  };

  for (const key of candidateKeys) {
    const encodedPath = key.split('/').map(encodeURIComponent).join('/');
    const b2Url = `${B2_DOWNLOAD_BASE}/file/${B2_BUCKET_NAME}/${encodedPath}?Authorization=${token}`;
    try {
      const b2Res = await fetch(b2Url, {
        method: request.method,
        headers: forwardHeaders
      });
      if (b2Res.ok || b2Res.status === 206) {
        const respHeaders = new Headers(b2Res.headers);
        Object.entries(CORS_HEADERS).forEach(([k, v]) => respHeaders.set(k, v));
        respHeaders.set("Cache-Control", "public, max-age=2592000, s-maxage=2592000, immutable");
        respHeaders.set("Accept-Ranges", "bytes");
        const ct = respHeaders.get("content-type");
        if ((!ct || ct === "application/octet-stream" || ct.includes("b2")) && MIME_MAP[ext]) {
          respHeaders.set("Content-Type", MIME_MAP[ext]);
        }
        return new Response(request.method === "HEAD" ? null : b2Res.body, {
          status: b2Res.status,
          statusText: b2Res.statusText,
          headers: respHeaders
        });
      }
    } catch (e) {}
  }
  return null;
}

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
  const isStorageReq = (url.pathname.startsWith("/v1/storage/objects/") || url.pathname.startsWith("/s/")) && ["GET", "HEAD"].includes(request.method);

  // ⚡ 1. CLOUDFLARE EDGE CACHE LOOKUP (<10ms global hits)
  let cfCache = null;
  let cacheKey = null;
  if (isStorageReq && typeof caches !== "undefined" && caches.default) {
    try {
      cfCache = caches.default;
      cacheKey = new Request(url.toString(), request);
      const cached = await cfCache.match(cacheKey);
      if (cached) {
        return cached;
      }
    } catch (e) {}
  }

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
  // Storage requests are fast-fail: 3000ms timeout and single attempt before immediate B2 fallback
  const maxAttempts = isStorageReq ? 1 : 3;
  const isLongRunning = !isStorageReq && (
    url.pathname.includes("/speech") || 
    url.pathname.includes("/transcriptions") || 
    url.pathname.includes("/chat") || 
    url.pathname.includes("/inference")
  );
  const timeoutMs = isStorageReq ? 3000 : (isLongRunning ? 60000 : 15000);

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

      // Invalidate cache and retry on bad gateway / tunnel restart codes (non-storage only)
      if (!isStorageReq && [403, 502, 503, 504, 530].includes(response.status) && attempt < maxAttempts) {
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

  // ⚡ 2. Storage handling: seamless B2 fallback + edge caching
  if (isStorageReq) {
    if (response && [200, 206].includes(response.status)) {
      const respHeaders = new Headers(response.headers);
      Object.entries(CORS_HEADERS).forEach(([k, v]) => respHeaders.set(k, v));
      respHeaders.set("Cache-Control", "public, max-age=2592000, s-maxage=2592000, immutable");
      const edgeResp = new Response(request.method === "HEAD" ? null : response.body, {
        status: response.status,
        statusText: response.statusText,
        headers: respHeaders
      });
      if (cfCache && cacheKey) {
        try { await cfCache.put(cacheKey, edgeResp.clone()); } catch(e) {}
      }
      return edgeResp;
    }

    // Phone returned 404, 502, 503, or timed out -> try B2
    const b2Fallback = await tryB2StorageFallback(request, url);
    if (b2Fallback) {
      if (cfCache && cacheKey) {
        try { await cfCache.put(cacheKey, b2Fallback.clone()); } catch(e) {}
      }
      return b2Fallback;
    }

    // Object genuinely does not exist on Phone or B2 -> return fast empty 404 without JSON to prevent ORB (OpaqueResponseBlocking)
    return new Response(null, {
      status: 404,
      statusText: "Not Found",
      headers: {
        ...CORS_HEADERS,
        "Cache-Control": "public, max-age=60"
      }
    });
  }

  // 3. Fallback for non-storage items if tunnel is reconnecting
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
