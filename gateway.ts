// Unified Edge Gateway: Routes Nikolinus Cloud Stack + Xiaomi Redmi 9i Phone AI Datacenter
const PORT = Number(process.env.GATEWAY_PORT || 8000);
const PHONE_ORIGIN = process.env.PHONE_ORIGIN || "http://192.168.29.2:8080";

const NIKOLINUS_AUTH = "http://127.0.0.1:4001";
const NIKOLINUS_DB = "http://127.0.0.1:4002";
const NIKOLINUS_FN = "http://127.0.0.1:4003";

console.log(`[GATEWAY] Starting Unified Gateway on port ${PORT}`);
console.log(`[GATEWAY] Phone AI Origin: ${PHONE_ORIGIN}`);
console.log(`[GATEWAY] Nikolinus: Auth (:4001), Database (:4002), Functions (:4003)`);

function getTargetUrl(url: URL): string {
  const pathname = url.pathname;
  const search = url.search;

  // 1. Authentication routes
  if (pathname.startsWith("/authentication/")) {
    const stripped = pathname.replace("/authentication", "") || "/";
    return `${NIKOLINUS_AUTH}${stripped}${search}`;
  }
  if (["/signup", "/signin", "/refresh", "/signout", "/me"].includes(pathname)) {
    return `${NIKOLINUS_AUTH}${pathname}${search}`;
  }

  // 2. Database routes
  if (pathname.startsWith("/database/")) {
    const stripped = pathname.replace("/database", "") || "/";
    return `${NIKOLINUS_DB}${stripped}${search}`;
  }
  if (pathname.startsWith("/doc/") || pathname === "/query" || pathname === "/watch" || pathname.startsWith("/rules/")) {
    return `${NIKOLINUS_DB}${pathname}${search}`;
  }

  // 3. Functions routes
  if (pathname.startsWith("/functions/")) {
    const stripped = pathname.replace("/functions", "") || "/";
    return `${NIKOLINUS_FN}${stripped}${search}`;
  }
  if (pathname.startsWith("/call/")) {
    return `${NIKOLINUS_FN}${pathname}${search}`;
  }

  // 4. Everything else routes to the Phone AI Datacenter
  return `${PHONE_ORIGIN}${pathname}${search}`;
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

    const targetUrl = getTargetUrl(url);

    try {
      const headers = new Headers(req.headers);
      headers.set("host", new URL(targetUrl).host);

      const hasBody = !["GET", "HEAD"].includes(req.method);
      const res = await fetch(targetUrl, {
        method: req.method,
        headers,
        body: hasBody ? req.body : undefined,
        // @ts-ignore
        duplex: hasBody ? "half" : undefined
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
    } catch (err: any) {
      console.error(`[GATEWAY ERROR] Failed to proxy ${url.pathname} to ${targetUrl}:`, err.message);
      return new Response(JSON.stringify({ error: "Gateway Proxy Error", details: err.message }), {
        status: 502,
        headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" }
      });
    }
  }
};
