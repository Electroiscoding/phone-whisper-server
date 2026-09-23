import { handleRequest, handleOptions, CORS_HEADERS } from "./_proxy.js";

export const onRequestOptions = handleOptions;

export async function onRequest(context) {
  const { request, next } = context;
  const url = new URL(request.url);

  if (request.method === "OPTIONS") {
    return handleOptions(context);
  }

  const apiPrefixes = ["/v1/", "/auth/", "/s/", "/screen/"];
  const apiExactPaths = [
    "/inference", "/telemetry", "/tts", "/speech", "/health", 
    "/models", "/backends", "/register_tunnel", "/benchmark", 
    "/compress", "/decompress", "/acc", "/acc/info", "/acc/status", 
    "/acc/control", "/images/compress", "/image/compress", 
    "/images/info", "/image/info", "/compress/image", "/info/image", "/info/images"
  ];
  const isApi = apiPrefixes.some(prefix => url.pathname.startsWith(prefix)) || apiExactPaths.includes(url.pathname);

  if (!isApi) {
    return next();
  }

  return handleRequest(context);
}
