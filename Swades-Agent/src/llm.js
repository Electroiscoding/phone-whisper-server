import fs from 'fs';
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

function loadKeys() {
  const paths = [
    '/root/.openrouter_keys.json',
    '/data/data/com.termux/files/home/.openrouter_keys.json',
    process.env.HOME ? `${process.env.HOME}/.openrouter_keys.json` : null
  ].filter(Boolean);

  for (const p of paths) {
    if (fs.existsSync(p)) {
      try {
        const data = JSON.parse(fs.readFileSync(p, 'utf8'));
        if (data.keys && data.keys.length > 0) return data;
      } catch (e) {}
    }
  }
  return {
    keys: [],
    active_key_index: 0
  };
}

let keyVault = loadKeys();
let activeKeyIndex = keyVault.active_key_index || 0;

export async function callLLM(messages, options = {}) {
  let modelIndex = 0;
  let keyAttempts = 0;

  while (modelIndex < MODELS.length) {
    const currentModel = MODELS[modelIndex];
    const activeKey = options.apiKey || process.env.OPENROUTER_API_KEY || keyVault.keys[activeKeyIndex % keyVault.keys.length];

    try {
      const response = await fetch('https://openrouter.ai/api/v1/chat/completions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${activeKey}`
        },
        body: JSON.stringify({
          model: currentModel,
          messages,
          temperature: 0.2
        })
      });

      if (!response.ok) {
        const status = response.status;
        const errText = await response.text().catch(() => '');
        
        // Key rate limit or quota -> rotate key
        if (status === 429 && keyAttempts < keyVault.keys.length) {
          keyAttempts++;
          activeKeyIndex = (activeKeyIndex + 1) % keyVault.keys.length;
          llmEvents.emit('model_fallback', {
            message: `Key rate limited on ${currentModel}. Rotated to secondary key.`,
            error: errText
          });
          continue;
        }

        // Model error or fallback needed
        throw new Error(`API returned HTTP ${status}: ${errText.substring(0, 150)}`);
      }

      const data = await response.json();
      const content = data.choices?.[0]?.message?.content;
      if (!content) {
        throw new Error('Empty response from model');
      }
      return content;
    } catch (err) {
      const nextModelIndex = modelIndex + 1;
      if (nextModelIndex < MODELS.length) {
        const nextModel = MODELS[nextModelIndex];
        llmEvents.emit('model_fallback', {
          message: `Model ${currentModel} error (${err.message}). Falling back to ${nextModel}...`,
          error: err.message
        });
        modelIndex++;
        continue;
      } else {
        throw new Error(`All fallback models failed. Last error: ${err.message}`);
      }
    }
  }
}
