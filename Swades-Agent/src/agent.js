import fs from 'fs';
import path from 'path';
import { execSync } from 'child_process';
import { callLLM, llmEvents } from './llm.js';

export async function runAgent({ jobId, workspaceDir, payload, postEvent }) {
  await postEvent('thinking', { message: 'Agent started processing job' });
  
  // Example of LLM fallback listener
  llmEvents.on('model_fallback', (data) => {
    postEvent('thinking', { message: data.message });
  });

  let prompt = payload.task;
  let maxTurns = 5;
  let turn = 0;
  
  while (turn < maxTurns) {
    turn++;
    // Simulate LLM action generating some code changes
    // (In reality, it would call llm and run tools)
    
    // Self-Verification Step
    let verificationPassed = true;
    let diffOutput = '';
    let verificationError = '';

    try {
      diffOutput = execSync(`git diff`, { cwd: workspaceDir }).toString();
      const statOutput = execSync(`git diff --stat`, { cwd: workspaceDir }).toString();
      
      const changedFiles = execSync(`git diff --name-only`, { cwd: workspaceDir })
        .toString().split('\n').filter(Boolean);

      for (const file of changedFiles) {
        const fullPath = path.join(workspaceDir, file);
        if (file.endsWith('.js')) {
          execSync(`node --check ${fullPath}`);
        } else if (file.endsWith('.py')) {
          execSync(`python3 -m py_compile ${fullPath}`);
        } else if (file.endsWith('.json')) {
          execSync(`node -e "JSON.parse(fs.readFileSync('${fullPath}'))"`);
        }
      }
    } catch (err) {
      verificationPassed = false;
      verificationError = err.message || err.stderr?.toString() || 'Unknown syntax error';
    }

    if (verificationPassed) {
      await postEvent('verification', { passed: true, diff: diffOutput });
      // If done, exit loop
      break;
    } else {
      await postEvent('verification', { passed: false, error: verificationError });
      prompt = `Verification failed with error: ${verificationError}. Fix the syntax error immediately.`;
      // loop continues to fix it
    }
  }
}
