/**
 * Zero-Dependency OpenAI-Compatible Streaming LLM Client
 * Compatible with local Qwen 2.5 SLM (llama-server), OpenRouter, Groq, OpenAI, and DeepSeek.
 */
export async function callLLM(context, messages, tools) {
  const baseUrl = (context.baseUrl || 'http://127.0.0.1:8001/v1').replace(/\/+$/, '');
  const apiKey = context.apiKey || 'local';
  const model = context.model || 'qwen2.5';
  
  const endpoint = `${baseUrl}/chat/completions`;
  const payload = {
    model: model,
    messages: messages,
    tools: tools,
    tool_choice: 'auto',
    stream: true,
    temperature: 0
  };

  const headers = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${apiKey}`,
    'Accept': 'text/event-stream'
  };

  try {
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: headers,
      body: JSON.stringify(payload),
      signal: context.abortSignal
    });

    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`LLM API returned HTTP ${res.status}: ${errText}`);
    }

    let content = '';
    const toolCallsMap = new Map();
    
    const reader = res.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';

    while (true) {
      if (context.abortSignal && context.abortSignal.aborted) {
        reader.cancel();
        throw new Error('Aborted');
      }

      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith(':')) continue;
        if (trimmed === 'data: [DONE]') continue;

        if (trimmed.startsWith('data: ')) {
          try {
            const chunk = JSON.parse(trimmed.slice(6));
            const delta = chunk.choices?.[0]?.delta;
            if (!delta) continue;

            if (delta.content) {
              content += delta.content;
              if (context.onEvent) {
                context.onEvent({ type: 'thinking_chunk', data: delta.content });
              }
            }

            if (delta.tool_calls) {
              for (const tc of delta.tool_calls) {
                const idx = tc.index !== undefined ? tc.index : 0;
                if (!toolCallsMap.has(idx)) {
                  toolCallsMap.set(idx, {
                    id: tc.id || `call_${Date.now()}_${idx}`,
                    type: 'function',
                    function: { name: tc.function?.name || '', arguments: tc.function?.arguments || '' }
                  });
                } else {
                  const existing = toolCallsMap.get(idx);
                  if (tc.function?.name) existing.function.name += tc.function.name;
                  if (tc.function?.arguments) existing.function.arguments += tc.function.arguments;
                }
              }
            }
          } catch (jsonErr) {
            // Ignore parse errors on partial chunks
          }
        }
      }
    }

    const tool_calls = Array.from(toolCallsMap.values());
    const resultMessage = { role: 'assistant', content: content || null };
    if (tool_calls.length > 0) {
      resultMessage.tool_calls = tool_calls;
    }

    return resultMessage;
  } catch (err) {
    if (context.onEvent) {
      context.onEvent({ type: 'error', data: { message: err.message } });
    }
    throw err;
  }
}
