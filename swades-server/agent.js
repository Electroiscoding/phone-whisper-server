import { callLLM } from './llm.js';
import { SYSTEM_PROMPT, TOOL_SCHEMAS } from './prompts.js';
import { executeTool, indexCodebase } from './tools.js';

export async function runAgent(context, task) {
  const indexStr = indexCodebase(context);
  let messages = [
    { role: 'system', content: SYSTEM_PROMPT + '\\n\\nWorkspace: ' + context.workdir + '\\n\\nCodebase Index:\\n' + indexStr },
    { role: 'user', content: task }
  ];
  
  const filesChanged = new Set();
  let stepCount = 0;
  
  while (stepCount < 50) {
    if (context.abortSignal && context.abortSignal.aborted) {
      throw new Error('Agent execution cancelled');
    }
    
    const response = await callLLM(context, messages, TOOL_SCHEMAS);
    messages.push(response);
    
    if (!response.tool_calls || response.tool_calls.length === 0) {
      break;
    }
    
    for (const tc of response.tool_calls) {
      let args = {};
      try {
        args = JSON.parse(tc.function.arguments);
      } catch (e) {
        // Handled below
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
        context.onEvent({ type: 'tool_result', data: { name: tc.function.name, output: result.slice(0, 500) }, timestamp });
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
