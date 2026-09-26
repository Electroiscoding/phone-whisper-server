import { handleRequest, handleOptions, CORS_HEADERS, setLiveOrigin, getLiveOrigin } from "./_proxy.js";

export const onRequestOptions = handleOptions;

export async function onRequest(context) {
  const { request, next } = context;
  const url = new URL(request.url);

  if (request.method === "OPTIONS") {
    return handleOptions(context);
  }

  if (url.pathname === "/register_tunnel") {
    if (request.method === "POST") {
      try {
        const data = await request.clone().json();
        if (data && data.endpoint && data.secret === "mobile_ai_nuclear_key") {
          const origin = data.endpoint.replace(/\/+$/, "");
          setLiveOrigin(origin);
          return new Response(JSON.stringify({
            status: "registered",
            active_origin: origin,
            timestamp: Math.floor(Date.now() / 1000)
          }), {
            status: 200,
            headers: { ...CORS_HEADERS, "Content-Type": "application/json" }
          });
        }
      } catch (e) {}
    } else {
      const origin = await getLiveOrigin(false);
      return new Response(JSON.stringify({
        status: "ok",
        active_origin: origin,
        timestamp: Math.floor(Date.now() / 1000)
      }), {
        status: 200,
        headers: { ...CORS_HEADERS, "Content-Type": "application/json" }
      });
    }
  }

  const apiPrefixes = ["/v1/", "/auth/", "/s/", "/screen/"];
  const apiExactPaths = [
    "/inference", "/telemetry", "/tts", "/speech", "/health", 
    "/models", "/backends", "/benchmark", 
    "/compress", "/decompress", "/acc", "/acc/info", "/acc/status", 
    "/acc/control", "/images/compress", "/image/compress", 
    "/images/info", "/image/info", "/compress/image", "/info/image", "/info/images"
  ];
  const isApi = apiPrefixes.some(prefix => url.pathname.startsWith(prefix)) || apiExactPaths.includes(url.pathname);

  if (!isApi) {
    const res = await next();
    const newHeaders = new Headers(res.headers);
    Object.entries(CORS_HEADERS).forEach(([k, v]) => newHeaders.set(k, v));
    return new Response(res.body, {
      status: res.status,
      statusText: res.statusText,
      headers: newHeaders
    });
  }

  return handleRequest(context);
}
