// Unified Edge Gateway: Routes Nikolinus Cloud Stack + Xiaomi Redmi 9i Phone AI Datacenter + Host CPU Fallback
const PORT = Number(process.env.GATEWAY_PORT || 8000);
const PHONE_ORIGINS = [
  process.env.PHONE_ORIGIN || "http://192.168.29.2:8080",
  "http://127.0.0.1:8081"
];
const LOCAL_FALLBACK = process.env.LOCAL_ORIGIN || "http://127.0.0.1:8082";

const NIKOLINUS_AUTH = "http://127.0.0.1:4001";
const NIKOLINUS_DB = "http://127.0.0.1:4002";
const NIKOLINUS_FN = "http://127.0.0.1:4003";

console.log(`[GATEWAY] Starting Resilient Sovereign Gateway on port ${PORT}`);
console.log(`[GATEWAY] Primary Phone AI Origins: ${PHONE_ORIGINS.join(", ")}`);
console.log(`[GATEWAY] Local Sovereign Fallback: ${LOCAL_FALLBACK}`);
console.log(`[GATEWAY] Nikolinus: Auth (:4001), Database (:4002), Functions (:4003)`);

let lastHealthyPhone: string | null = null;
let lastPhoneProbe = 0;
const PROBE_INTERVAL_MS = 4000;

async function checkPhoneOnline(): Promise<string | null> {
  const now = Date.now();
  if (now - lastPhoneProbe < PROBE_INTERVAL_MS && lastHealthyPhone) {
    return lastHealthyPhone;
  }
  for (const origin of PHONE_ORIGINS) {
    try {
      const res = await fetch(`${origin}/health`, {
        signal: AbortSignal.timeout(800)
      });
      if (res.ok) {
        lastHealthyPhone = origin;
        lastPhoneProbe = now;
        return origin;
      }
    } catch (_) {}
  }
  lastHealthyPhone = null;
  lastPhoneProbe = now;
  return null;
}

export default {
  port: PORT,
  idleTimeout: 120,
  async fetch(req: Request) {
    const url = new URL(req.url);

    // Preflight CORS
    if (req.method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS, HEAD",
          "Access-Control-Allow-Headers": "Content-Type, Authorization, x-service-key, x-api-key, *",
          "Access-Control-Max-Age": "86400",
        }
      });
    }

    const pathname = url.pathname;
    const search = url.search;

    // 1. Nikolinus Authentication routes
    if (pathname.startsWith("/authentication/") || ["/signup", "/signin", "/refresh", "/signout", "/me"].includes(pathname)) {
      const stripped = pathname.startsWith("/authentication") ? (pathname.replace("/authentication", "") || "/") : pathname;
      return proxyTo(`${NIKOLINUS_AUTH}${stripped}${search}`, req, null);
    }

    // 2. Nikolinus Database routes
    if (pathname.startsWith("/database/") || pathname.startsWith("/doc/") || pathname === "/query" || pathname === "/watch" || pathname.startsWith("/rules/")) {
      const stripped = pathname.startsWith("/database") ? (pathname.replace("/database", "") || "/") : pathname;
      return proxyTo(`${NIKOLINUS_DB}${stripped}${search}`, req, null);
    }

    // 3. Nikolinus Functions routes
    if (pathname.startsWith("/functions/") || pathname.startsWith("/call/")) {
      const stripped = pathname.startsWith("/functions") ? (pathname.replace("/functions", "") || "/") : pathname;
      return proxyTo(`${NIKOLINUS_FN}${stripped}${search}`, req, null);
    }

    // 4. Phone AI / Sovereign Datacenter routes (with seamless local fallback)
    const hasBody = !["GET", "HEAD"].includes(req.method);
    let bodyBuf: ArrayBuffer | null = null;
    if (hasBody) {
      try {
        bodyBuf = await req.arrayBuffer();
      } catch (_) {}
    }

    // Probe phone
    const phoneOrigin = await checkPhoneOnline();
    if (phoneOrigin) {
      try {
        const phoneUrl = `${phoneOrigin}${pathname}${search}`;
        const timeoutMs = pathname.includes("/execute") ? 300000 : (pathname.includes("/speech") ? 60000 : 10000);
        const res = await proxyTo(phoneUrl, req, bodyBuf, timeoutMs);
        if (res.status < 500) {
          return res;
        }
        console.warn(`[GATEWAY] Phone origin ${phoneOrigin} returned ${res.status}, falling back to local sovereign engine.`);
      } catch (err: any) {
        console.warn(`[GATEWAY] Phone origin ${phoneOrigin} failed: ${err.message}, falling back to local sovereign engine.`);
      }
    }

    // Local Host Fallback
    const localUrl = `${LOCAL_FALLBACK}${pathname}${search}`;
    try {
      return await proxyTo(localUrl, req, bodyBuf, 300000);
    } catch (localErr: any) {
      console.error(`[GATEWAY FATAL] Both Phone and Local Gateway failed for ${pathname}:`, localErr.message);
      return new Response(JSON.stringify({
        error: "Gateway Proxy Error",
        details: localErr.message,
        phone_status: phoneOrigin ? "unresponsive" : "offline",
        local_status: "error"
      }), {
        status: 502,
        headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" }
      });
    }
  }
};

async function proxyTo(targetUrl: string, req: Request, bodyBuf: ArrayBuffer | null, timeoutMs = 30000): Promise<Response> {
  const headers = new Headers(req.headers);
  headers.set("host", new URL(targetUrl).host);

  const res = await fetch(targetUrl, {
    method: req.method,
    headers,
    body: bodyBuf ? bodyBuf.slice(0) : undefined,
    // @ts-ignore
    duplex: bodyBuf ? "half" : undefined,
    signal: AbortSignal.timeout(timeoutMs)
  });

  const responseHeaders = new Headers(res.headers);
  responseHeaders.set("Access-Control-Allow-Origin", "*");
  responseHeaders.set("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS, HEAD");
  responseHeaders.set("Access-Control-Allow-Headers", "*");

  return new Response(res.body, {
    status: res.status,
    statusText: res.statusText,
    headers: responseHeaders
  });
}

