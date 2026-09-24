import { CORS_HEADERS, getLiveOrigin, tryB2StorageFallback } from "./_proxy.js";

export async function onRequest(context) {
  const { request } = context;
  const url = new URL(request.url);

  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: CORS_HEADERS });
  }

  let targetUrl = url.searchParams.get("url");
  if (!targetUrl) {
    return new Response(JSON.stringify({ error: "Missing ?url= parameter" }), {
      status: 400,
      headers: { ...CORS_HEADERS, "Content-Type": "application/json" }
    });
  }

  try {
    targetUrl = decodeURIComponent(targetUrl);

    // If targetUrl points to a trycloudflare quick-tunnel, rewrite to live origin
    let parsedTarget = null;
    try {
      parsedTarget = new URL(targetUrl);
      if (parsedTarget.hostname.includes("trycloudflare.com")) {
        const liveOrigin = await getLiveOrigin(false);
        if (liveOrigin && liveOrigin.startsWith("https://")) {
          targetUrl = `${liveOrigin}${parsedTarget.pathname}${parsedTarget.search}`;
          parsedTarget = new URL(targetUrl);
        }
      }
    } catch (e) {}

    const forwardHeaders = new Headers();
    if (request.headers.has("range")) {
      forwardHeaders.set("Range", request.headers.get("range"));
    }
    let response = await fetch(targetUrl, {
      method: request.method,
      headers: forwardHeaders
    }).catch(() => null);

    // If fetch failed or returned 404/5xx, try B2 storage fallback
    if (!response || !response.ok) {
      if (parsedTarget) {
        const b2Fallback = await tryB2StorageFallback(request, parsedTarget);
        if (b2Fallback) {
          return b2Fallback;
        }
      }
      if (!response) {
        return new Response(JSON.stringify({ error: "CORS proxy upstream fetch failed" }), {
          status: 502,
          headers: { ...CORS_HEADERS, "Content-Type": "application/json" }
        });
      }
    }

    const responseHeaders = new Headers(response.headers);
    Object.entries(CORS_HEADERS).forEach(([k, v]) => responseHeaders.set(k, v));
    responseHeaders.set("Cache-Control", "public, max-age=86400");

    return new Response(request.method === "HEAD" ? null : response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders
    });
  } catch (err) {
    return new Response(JSON.stringify({ error: "CORS proxy failed", details: String(err) }), {
      status: 502,
      headers: { ...CORS_HEADERS, "Content-Type": "application/json" }
    });
  }
}
