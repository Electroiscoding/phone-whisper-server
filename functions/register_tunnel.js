import { CORS_HEADERS, setLiveOrigin, getLiveOrigin, handleOptions } from "./_proxy.js";

export const onRequestOptions = handleOptions;

export async function onRequestPost(context) {
  try {
    const data = await context.request.json();
    if (data && data.endpoint && data.secret === "mobile_ai_nuclear_key") {
      const origin = data.endpoint.replace(/\/+$/, "");
      setLiveOrigin(origin);
      return new Response(JSON.stringify({
        status: "registered",
        active_origin: origin,
        timestamp: Math.floor(Date.now() / 1000)
      }), {
        status: 200,
        headers: {
          ...CORS_HEADERS,
          "Content-Type": "application/json"
        }
      });
    }
  } catch (e) {}

  return new Response(JSON.stringify({ status: "invalid_payload" }), {
    status: 400,
    headers: {
      ...CORS_HEADERS,
      "Content-Type": "application/json"
    }
  });
}

export async function onRequestGet(context) {
  const origin = await getLiveOrigin(false);
  return new Response(JSON.stringify({
    status: "ok",
    active_origin: origin,
    timestamp: Math.floor(Date.now() / 1000)
  }), {
    status: 200,
    headers: {
      ...CORS_HEADERS,
      "Content-Type": "application/json"
    }
  });
}
