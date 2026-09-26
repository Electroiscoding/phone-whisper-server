/**
 * SHARED PAGES FUNCTIONS PROXY UTILITY (functions/_proxy.js)
 * Automatically discovers live phone datacenter tunnel and reverse proxies requests.
 */

const GITHUB_ENDPOINT_URL = "https://raw.githubusercontent.com/Electroiscoding/phone-whisper-server/main/endpoint.json";
const GITHUB_API_ENDPOINT_URL = "https://api.github.com/repos/Electroiscoding/phone-whisper-server/contents/endpoint.json";
const JSDELIVR_ENDPOINT_URL = "https://cdn.jsdelivr.net/gh/Electroiscoding/phone-whisper-server@main/endpoint.json";
const DEFAULT_FALLBACK_ORIGIN = "https://mother-electric-represent-criticism.trycloudflare.com";

let cachedOrigin = null;
let lastFetchTime = 0;
const CACHE_TTL_MS = 15000;

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
  "Access-Control-Max-Age": "86400",
  "Cross-Origin-Resource-Policy": "cross-origin"
};

const B2_APP_KEY_ID = "0056b2f88b847c60000000003";
const B2_APP_KEY = "K005/3ZD3P9uF61mPNuuQjac1Yr0HMw";
const B2_BUCKET_ID = "866bf27f58e86b6894f70c16";
const B2_BUCKET_NAME = "netuark-storage";
const B2_DOWNLOAD_BASE = "https://f005.backblazeb2.com";

let cachedB2Token = null;
let b2TokenExpiry = 0;
let b2CircuitBreakerUntil = 0;

async function getB2DownloadToken() {
  const now = Date.now();
  if (now < b2CircuitBreakerUntil) {
    return null;
  }
  if (cachedB2Token && now < b2TokenExpiry) {
    return cachedB2Token;
  }
  try {
    const authHeader = "Basic " + btoa(B2_APP_KEY_ID + ":" + B2_APP_KEY);
    const authRes = await fetchWithTimeout("https://api.backblazeb2.com/b2api/v2/b2_authorize_account", {
      headers: { Authorization: authHeader }
    }, 2500);
    if (!authRes.ok) {
      if (authRes.status === 403 || authRes.status === 401) {
        b2CircuitBreakerUntil = now + (10 * 60 * 1000);
      }
      return null;
    }
    const authData = await authRes.json();
    const tokenRes = await fetchWithTimeout(authData.apiUrl + "/b2api/v2/b2_get_download_authorization", {
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
    }, 2500);
    if (!tokenRes.ok) {
      if (tokenRes.status === 403) {
        b2CircuitBreakerUntil = now + (10 * 60 * 1000);
      }
      return null;
    }
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

  if (Date.now() < b2CircuitBreakerUntil) {
    return null;
  }

  let rawFileName = url.pathname.split("/").pop() || "";
  try { rawFileName = decodeURIComponent(rawFileName); } catch (e) {}
  if (!rawFileName || rawFileName.includes(".trashed")) return null;

  const token = await getB2DownloadToken();
  if (!token) return null;

  const subPath = url.pathname.replace(/^\/(v1\/storage\/objects|s)\//, "");
  const candidateKeys = [];
  if (subPath) candidateKeys.push(subPath);
  if (!candidateKeys.includes(rawFileName)) candidateKeys.push(rawFileName);
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
    webm: 'video/webm',
    mp3: 'audio/mpeg',
    ogg: 'audio/ogg',
    m4a: 'audio/mp4',
    aac: 'audio/aac',
    flac: 'audio/flac',
    mp4: 'video/mp4',
    mov: 'video/quicktime',
    avi: 'video/x-msvideo',
    mkv: 'video/x-matroska',
    png: 'image/png',
    jpg: 'image/jpeg',
    jpeg: 'image/jpeg',
    webp: 'image/webp',
    gif: 'image/gif',
    svg: 'image/svg+xml',
    pdf: 'application/pdf'
  };

  for (const key of candidateKeys) {
    if (Date.now() < b2CircuitBreakerUntil) break;
    const encodedPath = key.split('/').map(encodeURIComponent).join('/');
    const b2Url = `${B2_DOWNLOAD_BASE}/file/${B2_BUCKET_NAME}/${encodedPath}?Authorization=${token}`;
    try {
      const b2Res = await fetchWithTimeout(b2Url, {
        method: request.method,
        headers: forwardHeaders
      }, 1500);

      if (b2Res.status === 403) {
        b2CircuitBreakerUntil = Date.now() + (10 * 60 * 1000);
        break;
      }

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

  // 1. Primary: Raw GitHub (fast, no rate limits)
  try {
    const res = await fetchWithTimeout(`${GITHUB_ENDPOINT_URL}?_t=${now}`, {
      headers: { "User-Agent": "Cloudflare-Pages-Functions/3.0", "Cache-Control": "no-cache, no-store, must-revalidate" }
    }, 4000);
    if (res.ok) {
      const data = await res.json();
      if (data && data.endpoint && data.endpoint.startsWith("https://")) {
        cachedOrigin = data.endpoint.replace(/\/+$/, "");
        lastFetchTime = now;
        return cachedOrigin;
      }
    }
  } catch (err) {}

  // 2. Secondary: GitHub API raw contents
  try {
    const ghApiRes = await fetchWithTimeout(GITHUB_API_ENDPOINT_URL, {
      headers: {
        "User-Agent": "Cloudflare-Pages-Functions/3.0",
        "Accept": "application/vnd.github.v3.raw",
        "Cache-Control": "no-cache, no-store, must-revalidate"
      }
    }, 4000);
    if (ghApiRes.ok) {
      const text = await ghApiRes.text();
      try {
        const data = JSON.parse(text);
        if (data && data.endpoint && data.endpoint.startsWith("https://")) {
          cachedOrigin = data.endpoint.replace(/\/+$/, "");
          lastFetchTime = now;
          return cachedOrigin;
        }
      } catch (pe) {}
    }
  } catch (err) {}

  return cachedOrigin || DEFAULT_FALLBACK_ORIGIN;
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

  try {
    const isStorageMutation = (url.pathname.startsWith("/v1/storage/objects/") || url.pathname.startsWith("/s/")) && ["PUT", "POST", "DELETE"].includes(request.method);
  if (isStorageMutation && typeof caches !== "undefined" && caches.default) {
    try {
      const purgeReq = new Request(url.toString(), { method: "GET" });
      if (typeof context.waitUntil === "function") {
        context.waitUntil(caches.default.delete(purgeReq));
      } else {
        caches.default.delete(purgeReq).catch(() => {});
      }
    } catch (e) {}
  }

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
  // Storage requests: ONLY 1 attempt (phone streams within ~1s when file exists; hangs when file is missing)
  const maxAttempts = isStorageReq ? 1 : 3;
  const isLongRunning = !isStorageReq && (
    url.pathname.includes("/speech") || 
    url.pathname.includes("/transcriptions") || 
    url.pathname.includes("/chat") || 
    url.pathname.includes("/inference")
  );
  // Storage requests timeout at 3000ms. If phone hasn't answered in 3s, it does not exist or tunnel stalled.
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

      // Invalidate cache and retry on bad gateway / tunnel restart codes
      if ([403, 502, 503, 504, 530].includes(response.status) && attempt < maxAttempts) {
        cachedOrigin = null;
        await new Promise(r => setTimeout(r, attempt * 150));
        origin = await getLiveOrigin(true);
        targetUrl = `${origin}${url.pathname}${url.search}`;
        continue;
      }

      break;
    } catch (fetchErr) {
      if (attempt < maxAttempts) {
        cachedOrigin = null;
        await new Promise(r => setTimeout(r, attempt * 150));
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
      respHeaders.set("Accept-Ranges", "bytes");
      // Ensure correct Content-Type to prevent ORB (OpaqueResponseBlocking)
      const rawFileName = decodeURIComponent(url.pathname.split("/").pop() || "");
      const ext = (rawFileName.split('.').pop() || '').toLowerCase();
      const STORAGE_MIME = {
        wav:'audio/wav',webm:'video/webm',mp3:'audio/mpeg',ogg:'audio/ogg',
        m4a:'audio/mp4',aac:'audio/aac',mp4:'video/mp4',mov:'video/quicktime',
        png:'image/png',jpg:'image/jpeg',jpeg:'image/jpeg',webp:'image/webp',
        gif:'image/gif',svg:'image/svg+xml',pdf:'application/pdf'
      };
      const ct = respHeaders.get("content-type");
      if ((!ct || ct === "application/octet-stream") && STORAGE_MIME[ext]) {
        respHeaders.set("Content-Type", STORAGE_MIME[ext]);
      }
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

    // Object genuinely does not exist on Phone or B2 -> return fast clean 404 with CORS and cache at Edge
    const rawFileName = decodeURIComponent(url.pathname.split("/").pop() || "");
    const ext = (rawFileName.split('.').pop() || '').toLowerCase();
    const STORAGE_MIME = {
      wav:'audio/wav',webm:'video/webm',mp3:'audio/mpeg',ogg:'audio/ogg',
      m4a:'audio/mp4',aac:'audio/aac',mp4:'video/mp4',mov:'video/quicktime',
      png:'image/png',jpg:'image/jpeg',jpeg:'image/jpeg',webp:'image/webp',
      gif:'image/gif',svg:'image/svg+xml',pdf:'application/pdf'
    };
    const notFoundHeaders = {
      ...CORS_HEADERS,
      "Cache-Control": "public, max-age=86400, s-maxage=86400",
      "Content-Type": STORAGE_MIME[ext] || "application/octet-stream",
      "X-Debug-Origin": origin || "empty",
      "X-Debug-Target-Url": targetUrl || "empty",
      "X-Debug-Upstream-Status": response ? String(response.status) : "no_resp"
    };
    const notFoundResp = new Response("Not Found", {
      status: 404,
      statusText: "Not Found",
      headers: notFoundHeaders
    });
    if (cfCache && cacheKey) {
      try { await cfCache.put(cacheKey, notFoundResp.clone()); } catch(e) {}
    }
    return notFoundResp;
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
  } catch (fatalErr) {
    const isStorageReq = (url.pathname.startsWith("/v1/storage/objects/") || url.pathname.startsWith("/s/")) && ["GET", "HEAD"].includes(request.method);
    if (isStorageReq) {
      return new Response("Not Found", {
        status: 404,
        headers: {
          ...CORS_HEADERS,
          "Content-Type": "application/octet-stream",
          "Cache-Control": "public, max-age=3600"
        }
      });
    }
    return new Response(JSON.stringify({ error: "Edge gateway exception", details: String(fatalErr) }), {
      status: 502,
      headers: {
        ...CORS_HEADERS,
        "Content-Type": "application/json"
      }
    });
  }
}
