import { callLLM } from './llm.js';
import { SYSTEM_PROMPT, TOOL_SCHEMAS } from './prompts.js';
import { executeTool, indexCodebase } from './tools.js';

export async function runAgent(context, task) {
  if (context.onEvent) {
    context.onEvent({ type: 'status', data: '📂 Scanning and indexing repository workspace...' });
  }
  
  const indexStr = indexCodebase(context);
  let messages = [
    { role: 'system', content: SYSTEM_PROMPT + '\n\nWorkspace: ' + context.workdir + '\n\nCodebase Index:\n' + indexStr },
    { role: 'user', content: task }
  ];
  
  const filesChanged = new Set();
  let stepCount = 0;
  
  while (stepCount < 50) {
    if (context.abortSignal && context.abortSignal.aborted) {
      throw new Error('Agent execution cancelled');
    }

    const providerType = (context.baseUrl && context.baseUrl.includes('127.0.0.1')) ? 'Local Phone CPU' : 'Cloud Provider';
    if (context.onEvent) {
      context.onEvent({
        type: 'status',
        data: `🧠 [Step ${stepCount + 1}] Prompting ${context.model} (${providerType}) — evaluating context...`
      });
    }
    
    const response = await callLLM(context, messages, TOOL_SCHEMAS);
    messages.push(response);
    
    if (!response.tool_calls || response.tool_calls.length === 0) {
      if (context.onEvent) {
        context.onEvent({ type: 'status', data: `✨ Solution finalized by ${context.model}.` });
      }
      break;
    }
    
    for (const tc of response.tool_calls) {
      let args = {};
      try {
        args = JSON.parse(tc.function.arguments);
      } catch (e) {
        args = { raw: tc.function.arguments };
      }
      
      const timestamp = new Date().toISOString();
      if (context.onEvent) {
        context.onEvent({ type: 'tool_call', data: { name: tc.function.name, args }, timestamp });
      }
      
      let result;
      try {
        result = await executeTool(context, tc.function.name, args);
        if (['write_file', 'patch_file'].includes(tc.function.name) && args.path) {
          filesChanged.add(args.path);
        }
      } catch (e) {
        result = `Execution Error: ${e.message}`;
      }
      
      if (context.onEvent) {
        context.onEvent({ type: 'tool_result', data: { name: tc.function.name, output: result.slice(0, 4000) }, timestamp });
      }
      
      messages.push({ role: 'tool', tool_call_id: tc.id, content: result });
    }
    
    stepCount++;
    
    if (messages.length > 40) {
      messages = [messages[0], ...messages.slice(-20)];
    }
  }
  
  const finalContent = messages[messages.length - 1].content || 'No summary provided.';
  
  return {
    summary: finalContent,
    filesChanged: Array.from(filesChanged),
    totalSteps: stepCount
  };
}
