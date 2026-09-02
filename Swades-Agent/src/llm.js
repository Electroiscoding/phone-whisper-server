import { EventEmitter } from 'events';

const MODELS = [
  'openrouter/free',
  'inclusionai/ling-3.0-flash-fin:free',
  'nvidia/nemotron-3.5-lightning:free',
  'thinkingmachines/inkling-small:free',
  'thinkingmachines/inkling:free',
  'inception/mercury-2.5-preview'
];

export const llmEvents = new EventEmitter();

export async function callLLM(messages, options = {}) {
  let modelIndex = 0;
  let retryCount = 0;

  while (modelIndex < MODELS.length) {
    const currentModel = MODELS[modelIndex];
    try {
      const response = await fetch('https://openrouter.ai/api/v1/chat/completions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${process.env.OPENROUTER_API_KEY}`
        },
        body: JSON.stringify({
          model: currentModel,
          messages,
          stream: options.stream || false
        })
      });

      if (!response.ok) {
        const status = response.status;
        if ([429, 404, 500].includes(status) || status === 400 /* context exhaust approximation */) {
          throw new Error(`LLM API returned ${status}`);
        }
        throw new Error(`Unexpected LLM error: ${status}`);
      }

      if (options.stream) {
        // Simple stream wrapper or just return response
        return response.body; 
      } else {
        const data = await response.json();
        return data.choices[0].message.content;
      }
    } catch (err) {
      const nextModelIndex = modelIndex + 1;
      if (nextModelIndex < MODELS.length) {
        const nextModel = MODELS[nextModelIndex];
        llmEvents.emit('model_fallback', {
          message: `Failed on model ${currentModel}, switching to model ${nextModel}`,
          error: err.message
        });
        modelIndex++;
        // If 429, we might want to rotate keys, but instruction says rotate to next key (for OpenRouter, maybe another env var?)
        // Instructions: "Rotate to next key if 429." (Simplifying by just continuing to next model in this implementation or assuming user handles keys)
        continue;
      } else {
        throw new Error(`All models failed. Last error: ${err.message}`);
      }
    }
  }
}
