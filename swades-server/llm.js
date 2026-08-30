import OpenAI from 'openai';

export async function callLLM(context, messages, tools) {
  const baseUrl = context.baseUrl || 'http://127.0.0.1:8001/v1';
  const apiKey = context.apiKey || 'local';
  const model = context.model || 'qwen2.5';
  
  const client = new OpenAI({
    baseURL: baseUrl,
    apiKey: apiKey
  });

  try {
    const stream = await client.chat.completions.create({
      model: model,
      messages: messages,
      tools: tools,
      tool_choice: 'auto',
      stream: true,
      temperature: 0
    }, { signal: context.abortSignal });

    let content = '';
    const toolCallsMap = new Map();

    for await (const chunk of stream) {
      if (context.abortSignal && context.abortSignal.aborted) {
        throw new Error('Aborted');
      }

      const delta = chunk.choices[0]?.delta;
      if (!delta) continue;

      if (delta.content) {
        content += delta.content;
        if (context.onEvent) {
          context.onEvent({ type: 'thinking', data: delta.content });
        }
      }

      if (delta.tool_calls) {
        for (const tc of delta.tool_calls) {
          if (!toolCallsMap.has(tc.index)) {
            toolCallsMap.set(tc.index, {
              id: tc.id,
              type: 'function',
              function: { name: tc.function.name, arguments: tc.function.arguments || '' }
            });
          } else {
            const existing = toolCallsMap.get(tc.index);
            if (tc.function?.arguments) {
              existing.function.arguments += tc.function.arguments;
            }
          }
        }
      }
    }

    const tool_calls = Array.from(toolCallsMap.values());
    
    if (context.onEvent && tool_calls.length > 0) {
      for (const tc of tool_calls) {
        let args = {};
        try {
          args = JSON.parse(tc.function.arguments);
        } catch (e) {
          // invalid json, let it be handled later
        }
        context.onEvent({ type: 'tool_call', data: { name: tc.function.name, args } });
      }
    }

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
