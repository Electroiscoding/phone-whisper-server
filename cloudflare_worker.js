/**
 * ☢️ NUCLEAR CLOUDFLARE EDGE WORKER
 * Self-Healing Dynamic Failover & Universal Reverse Proxy with GitHub OAuth for Swades Agent
 */

const JSDELIVR_ENDPOINT_URL = "https://cdn.jsdelivr.net/gh/Electroiscoding/phone-whisper-server@main/endpoint.json";
const GITHUB_ENDPOINT_URL = "https://raw.githubusercontent.com/Electroiscoding/phone-whisper-server/main/endpoint.json";
const SHARED_SECRET = "mobile_ai_nuclear_key";

// GitHub OAuth App Credentials (configured via Cloudflare Worker Secrets / Environment Variables)
const getClientId = (env) => (env && env.GITHUB_CLIENT_ID) || "";
const getClientSecret = (env) => (env && env.GITHUB_CLIENT_SECRET) || "";

// In-Memory Edge Cache for Active Tunnel Target
let cachedOrigin = "https://ocean-color-referrals-reg.trycloudflare.com";
let lastFetchTime = Date.now();
const CACHE_TTL_MS = 60000; // 60 seconds

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, HEAD",
  "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With, Accept, Origin, Cache-Control, X-Accel-Buffering, x-api-key, *",
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

async function getLiveOrigin(forceRefresh = false) {
  const now = Date.now();
  if (!forceRefresh && cachedOrigin && (now - lastFetchTime < CACHE_TTL_MS)) {
    return cachedOrigin;
  }

  // 1. Primary: Raw GitHub CDN (Real-time, instant commit sync)
  try {
    const res = await fetchWithTimeout(`${GITHUB_ENDPOINT_URL}?_t=${now}`, {
      headers: { "User-Agent": "Cloudflare-Edge-Worker/2.0", "Cache-Control": "no-cache, no-store, must-revalidate" },
      cf: { cacheTtl: 0, cacheEverything: false }
    }, 2500);
    if (res.ok) {
      const data = await res.json();
      if (data.endpoint && data.endpoint.startsWith("https://")) {
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
    }, 2500);
    if (jsdelivrRes.ok) {
      const data = await jsdelivrRes.json();
      if (data && data.endpoint && data.endpoint.startsWith("https://")) {
        cachedOrigin = data.endpoint.replace(/\/+$/, "");
        lastFetchTime = now;
        return cachedOrigin;
      }
    }
  } catch (err) {}

  return cachedOrigin || "https://interesting-unexpected-interval-bedroom.trycloudflare.com";
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

    // =========================================================================
    // 🐙 GITHUB OAUTH AUTHENTICATION HANDLERS (SWADES AGENT)
    // =========================================================================
    
    // (A) Redirect to GitHub OAuth Authorization Page
    if (["/auth/github/login", "/login"].includes(url.pathname)) {
      const authUrl = `https://github.com/login/oauth/authorize?client_id=${getClientId(env)}&scope=repo,read:user`;
      return Response.redirect(authUrl, 302);
    }

    // (B) OAuth Callback from GitHub
    if (["/auth/github/callback", "/session", "/callback", "/auth/callback"].includes(url.pathname)) {
      const code = url.searchParams.get("code");
      if (!code) {
        return new Response("Missing OAuth code from GitHub.", { status: 400 });
      }

      try {
        // 1. Exchange code for access token
        const tokenRes = await fetch("https://github.com/login/oauth/access_token", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "SwadesAgent/1.0"
          },
          body: JSON.stringify({
            client_id: getClientId(env),
            client_secret: getClientSecret(env),
            code: code
          })
        });

        const tokenData = await tokenRes.json();
        if (!tokenData.access_token) {
          return new Response(`OAuth Error: ${tokenData.error_description || JSON.stringify(tokenData)}`, { status: 400 });
        }

        const accessToken = tokenData.access_token;

        // 2. Fetch authenticated user profile
        let userProfile = { login: "github_user", avatar_url: "" };
        try {
          const userRes = await fetch("https://api.github.com/user", {
            headers: {
              "Authorization": `Bearer ${accessToken}`,
              "User-Agent": "SwadesAgent/1.0"
            }
          });
          if (userRes.ok) {
            userProfile = await userRes.json();
          }
        } catch (e) {}

        // 3. Return clean HTML popup bridge or redirect
        const authPayload = JSON.stringify({
          token: accessToken,
          username: userProfile.login,
          avatar: userProfile.avatar_url,
          name: userProfile.name || userProfile.login
        });

        const htmlResponse = `<!DOCTYPE html>
<html>
<head>
  <title>Connecting GitHub to Swades Agent...</title>
  <style>
    body { background: #07090e; color: #38bdf8; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; text-align: center; }
    .box { background: rgba(16, 22, 38, 0.9); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 16px; padding: 2rem; max-width: 400px; }
  </style>
</head>
<body>
  <div class="box">
    <h2>🐙 GitHub Connected!</h2>
    <p>Logged in as <strong>@${userProfile.login}</strong></p>
    <p style="font-size: 0.85rem; color: #94a3b8;">Redirecting back to PhoneWhisper...</p>
  </div>
  <script>
    const auth = ${authPayload};
    try {
      localStorage.setItem("gh_auth", JSON.stringify(auth));
      if (window.opener && !window.opener.closed) {
        window.opener.postMessage({ type: "GITHUB_AUTH", auth: auth }, "*");
        setTimeout(() => window.close(), 800);
      } else {
        window.location.href = "https://phone-whisper-server.pages.dev/";
      }
    } catch (e) {
      window.location.href = "https://phone-whisper-server.pages.dev/";
    }
  </script>
</body>
</html>`;

        return new Response(htmlResponse, {
          headers: { "Content-Type": "text/html; charset=utf-8" }
        });
      } catch (err) {
        return new Response(`Authentication failed: ${err.message}`, { status: 500 });
      }
    }

    // (C) Proxy User Repositories for Auto-complete
    if (url.pathname === "/auth/github/user-repos") {
      const authHeader = request.headers.get("Authorization");
      if (!authHeader) {
        return new Response(JSON.stringify({ error: "Unauthorized" }), {
          status: 401,
          headers: { ...CORS_HEADERS, "Content-Type": "application/json" }
        });
      }

      try {
        const repoRes = await fetch("https://api.github.com/user/repos?sort=updated&per_page=30", {
          headers: {
            "Authorization": authHeader,
            "User-Agent": "SwadesAgent/1.0",
            "Accept": "application/vnd.github.v3+json"
          }
        });
        const repos = await repoRes.json();
        return new Response(JSON.stringify(repos), {
          headers: { ...CORS_HEADERS, "Content-Type": "application/json" }
        });
      } catch (err) {
        return new Response(JSON.stringify({ error: err.message }), {
          status: 500,
          headers: { ...CORS_HEADERS, "Content-Type": "application/json" }
        });
      }
    }

    // 2. Direct Tunnel Registration from Phone (Instant Zero-Delay Registration)
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

    // 3. Proxy Request to Origin with Auto-Retry
    let origin = await getLiveOrigin(false);
    let targetUrl = `${origin}${url.pathname}${url.search}`;

    let response = null;
    let attempt = 0;

    const isLongRunning = url.pathname.includes("/speech") || 
                          url.pathname.includes("/transcriptions") || 
                          url.pathname.includes("/chat") || 
                          url.pathname.includes("/agent") ||
                          url.pathname.includes("/inference");
    const timeoutMs = isLongRunning ? 30000 : 8000;

    while (attempt < 3) {
      attempt++;
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

        const proxyReq = new Request(targetUrl, {
          method: request.method,
          headers: request.headers,
          body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
          redirect: "follow",
          signal: controller.signal
        });

        response = await fetch(proxyReq);
        clearTimeout(timeoutId);

        // If origin returned 502, 503, 504, 530, force-refresh endpoint and retry
        if ([502, 503, 504, 530].includes(response.status) && attempt < 3) {
          cachedOrigin = null;
          await new Promise(r => setTimeout(r, attempt * 250));
          origin = await getLiveOrigin(true);
          targetUrl = `${origin}${url.pathname}${url.search}`;
          continue;
        }

        break;
      } catch (fetchErr) {
        if (attempt < 3) {
          cachedOrigin = null;
          await new Promise(r => setTimeout(r, attempt * 300));
          origin = await getLiveOrigin(true);
          targetUrl = `${origin}${url.pathname}${url.search}`;
          continue;
        }
      }
    }

    // 4. Structured JSON Fallback if Phone is Temporarily Reconnecting
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

    // 5. Attach Full CORS Headers to Phone Response
    const responseHeaders = new Headers(response.headers);
    Object.entries(CORS_HEADERS).forEach(([k, v]) => responseHeaders.set(k, v));

    return new Response(request.method === "HEAD" ? null : response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders
    });
  }
};
