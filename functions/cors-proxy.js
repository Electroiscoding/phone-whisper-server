import { CORS_HEADERS } from "./_proxy.js";

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
    const forwardHeaders = new Headers();
    if (request.headers.has("range")) {
      forwardHeaders.set("Range", request.headers.get("range"));
    }
    const response = await fetch(targetUrl, {
      method: request.method,
      headers: forwardHeaders
    });

    const responseHeaders = new Headers(response.headers);
    Object.entries(CORS_HEADERS).forEach(([k, v]) => responseHeaders.set(k, v));
    responseHeaders.set("Cache-Control", "public, max-age=86400");
    if (responseHeaders.has("Content-Type") && responseHeaders.get("Content-Type").includes("text/html")) {
      // Don't override binary media types
    }

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
