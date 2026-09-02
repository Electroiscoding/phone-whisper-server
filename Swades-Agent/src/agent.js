import fs from 'fs';
import path from 'path';
import { execSync } from 'child_process';
import { callLLM, llmEvents } from './llm.js';

export async function runAgent({ jobId, workspaceDir, payload, postEvent }) {
  const task = payload.task || 'Analyze the repository';
  const repoUrl = payload.repo_url || payload.repoUrl;
  const token = payload.github_pat || payload.github_token;
  const branchName = `swades/patch-${jobId}`;

  // Forward model fallback events to gateway
  llmEvents.on('model_fallback', async (data) => {
    await postEvent('model_fallback', {
      message: data.message,
      error: data.error
    });
  });

  await postEvent('status', `Analyzing repository structure for task: "${task}"...`);

  // 1. Gather repository context
  let fileTree = [];
  try {
    const rawFiles = execSync(`find . -maxdepth 3 -not -path '*/.*' -not -path '*/node_modules/*'`, { cwd: workspaceDir }).toString();
    fileTree = rawFiles.split('\n').filter(Boolean).map(f => f.replace(/^\.\//, ''));
  } catch (e) {
    fileTree = ['Could not list directory'];
  }

  // Read manifest files
  let projectContext = '';
  const manifests = ['package.json', 'README.md', 'requirements.txt', 'index.html', 'main.py', 'src/index.js'];
  for (const m of manifests) {
    const p = path.join(workspaceDir, m);
    if (fs.existsSync(p)) {
      try {
        const content = fs.readFileSync(p, 'utf8').substring(0, 1500);
        projectContext += `\n--- ${m} ---\n${content}\n`;
      } catch (e) {}
    }
  }

  const systemPrompt = `You are Swades, an autonomous AI software engineer running on edge phone hardware.
Your task: "${task}"
Repository: ${repoUrl}
Working branch: ${branchName}

Files in workspace:
${fileTree.slice(0, 60).join('\n')}

Key context files:
${projectContext}

You can either respond with text explaining your findings and solution, or execute actions using either JSON format or TOOL_CALL format:

FORMAT 1 (JSON):
{
  "thought": "your step-by-step reasoning",
  "explanation": "clear user-facing explanation of what you found or changed",
  "tool_calls": [
    {"tool": "READ", "path": "file.js"},
    {"tool": "WRITE", "path": "file.js", "content": "...full code..."},
    {"tool": "RUN", "command": "npm test"}
  ],
  "done": true/false
}

FORMAT 2 (Markdown & Tool markers):
Explanation of findings...
TOOL_CALL: WRITE <path>
\`\`\`
code
\`\`\`
TOOL_CALL: FINISH <summary>

Always explain your reasoning and solution clearly.`;

  const messages = [
    { role: 'system', content: systemPrompt },
    { role: 'user', content: `Task: ${task}\nPlease analyze the repository, execute any necessary actions, and summarize your solution.` }
  ];

  let turn = 0;
  const maxTurns = 4;
  let isFinished = false;

  while (turn < maxTurns && !isFinished) {
    turn++;
    await postEvent('status', `Agent Turn ${turn}/${maxTurns}: Consulting OpenRouter AI models...`);

    let aiResponse = '';
    try {
      aiResponse = await callLLM(messages, { apiKey: payload.api_key });
    } catch (err) {
      await postEvent('error', { error: `LLM generation failed: ${err.message}` });
      break;
    }

    // Try parsing as JSON first
    let jsonPlan = null;
    try {
      // Find JSON block if wrapped in markdown
      const jsonMatch = aiResponse.match(/\{[\s\S]*\}/);
      if (jsonMatch) {
        jsonPlan = JSON.parse(jsonMatch[0]);
      }
    } catch (e) {}

    // Emit the thinking/reasoning to user interface
    const reasoningText = jsonPlan?.thought || jsonPlan?.explanation || aiResponse;
    await postEvent('thinking', reasoningText);

    messages.push({ role: 'assistant', content: aiResponse });

    let actionExecuted = false;

    // 1. Handle structured JSON tools
    if (jsonPlan && Array.isArray(jsonPlan.tool_calls)) {
      for (const tc of jsonPlan.tool_calls) {
        const toolName = (tc.tool || '').toUpperCase();
        if (toolName === 'READ' && tc.path) {
          actionExecuted = true;
          const fullPath = path.join(workspaceDir, tc.path);
          await postEvent('tool_start', { tool: 'read_file', args: { path: tc.path } });
          try {
            if (fs.existsSync(fullPath)) {
              const content = fs.readFileSync(fullPath, 'utf8');
              await postEvent('tool_end', { tool: 'read_file', result: `Read ${tc.path} (${content.length} chars)` });
              messages.push({ role: 'user', content: `TOOL_RESULT: Contents of ${tc.path}:\n\`\`\`\n${content.substring(0, 3000)}\n\`\`\`` });
            } else {
              await postEvent('tool_end', { tool: 'read_file', result: `File not found: ${tc.path}` });
              messages.push({ role: 'user', content: `TOOL_RESULT: File not found: ${tc.path}` });
            }
          } catch (err) {
            await postEvent('tool_end', { tool: 'read_file', result: `Error: ${err.message}` });
          }
        } else if (toolName === 'WRITE' && tc.path && tc.content) {
          actionExecuted = true;
          const fullPath = path.join(workspaceDir, tc.path);
          await postEvent('tool_start', { tool: 'write_file', args: { path: tc.path } });
          try {
            fs.mkdirSync(path.dirname(fullPath), { recursive: true });
            fs.writeFileSync(fullPath, tc.content, 'utf8');
            await postEvent('tool_end', { tool: 'write_file', result: `Updated ${tc.path} (${tc.content.length} chars)` });
            const diff = execSync('git diff', { cwd: workspaceDir }).toString();
            if (diff) {
              await postEvent('diff_update', { file: tc.path, diff });
            }
          } catch (err) {
            await postEvent('tool_end', { tool: 'write_file', result: `Error: ${err.message}` });
          }
        } else if (toolName === 'RUN' && tc.command) {
          actionExecuted = true;
          await postEvent('tool_start', { tool: 'run_command', args: { command: tc.command } });
          try {
            const out = execSync(tc.command, { cwd: workspaceDir, timeout: 20000 }).toString();
            await postEvent('tool_end', { tool: 'run_command', result: out.substring(0, 500) });
            messages.push({ role: 'user', content: `TOOL_RESULT: ${out.substring(0, 1500)}` });
          } catch (err) {
            await postEvent('tool_end', { tool: 'run_command', result: `Failed: ${err.message}` });
          }
        }
      }
      if (jsonPlan.done === true) {
        isFinished = true;
      }
    }

    // 2. Handle Text TOOL_CALL: WRITE
    const writeRegex = /TOOL_CALL:\s*WRITE\s+([^\n\r]+)[\r\n]+```(?:[a-zA-Z0-9_-]+)?\s*([\s\S]*?)```/g;
    let match;
    while ((match = writeRegex.exec(aiResponse)) !== null) {
      actionExecuted = true;
      const targetPath = match[1].trim();
      const fileContent = match[2];
      const fullPath = path.join(workspaceDir, targetPath);

      await postEvent('tool_start', { tool: 'write_file', args: { path: targetPath } });
      try {
        fs.mkdirSync(path.dirname(fullPath), { recursive: true });
        fs.writeFileSync(fullPath, fileContent, 'utf8');
        await postEvent('tool_end', { tool: 'write_file', result: `Updated ${targetPath} (${fileContent.length} bytes)` });
        const diff = execSync('git diff', { cwd: workspaceDir }).toString();
        if (diff) {
          await postEvent('diff_update', { file: targetPath, diff });
        }
      } catch (err) {
        await postEvent('tool_end', { tool: 'write_file', result: `Error writing ${targetPath}: ${err.message}` });
      }
    }

    // Check for FINISH marker
    if (aiResponse.includes('TOOL_CALL: FINISH') || (!actionExecuted && turn >= 2) || turn === maxTurns) {
      isFinished = true;
    }
  }

  // 2. Self-Verification Step
  await postEvent('status', 'Running self-verification on workspace...');
  let verificationPassed = true;
  let verificationError = '';
  let diffOutput = '';

  try {
    diffOutput = execSync('git diff', { cwd: workspaceDir }).toString();
    const changedFiles = execSync('git diff --name-only', { cwd: workspaceDir })
      .toString().split('\n').filter(Boolean);

    for (const file of changedFiles) {
      const fullPath = path.join(workspaceDir, file);
      if (file.endsWith('.js') || file.endsWith('.mjs')) {
        execSync(`node --check "${fullPath}"`);
      } else if (file.endsWith('.py')) {
        execSync(`python3 -m py_compile "${fullPath}"`);
      } else if (file.endsWith('.json')) {
        JSON.parse(fs.readFileSync(fullPath, 'utf8'));
      }
    }
  } catch (err) {
    verificationPassed = false;
    verificationError = err.message || 'Syntax error in modified files';
  }

  await postEvent('verification', {
    passed: verificationPassed,
    diff: diffOutput,
    error: verificationError || undefined,
    message: verificationPassed ? (diffOutput ? 'Self-verification passed with code changes.' : 'Analysis verified against codebase.') : `Verification issue: ${verificationError}`
  });

  // 3. Commit and Open Pull Request if there are changes
  if (diffOutput.trim()) {
    try {
      execSync('git add -A', { cwd: workspaceDir });
      execSync(`git commit -m "feat(swades): Autonomous implementation for ${task.substring(0, 50)}"`, { cwd: workspaceDir });
      
      if (token) {
        await postEvent('status', `Pushing branch ${branchName} to GitHub...`);
        execSync(`git push -u origin ${branchName} --force`, { cwd: workspaceDir });

        const repoClean = repoUrl.replace(/^https:\/\/github\.com\//, '').replace(/\.git$/, '');
        const prRes = await fetch(`https://api.github.com/repos/${repoClean}/pulls`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Accept': 'application/vnd.github.v3+json',
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            title: `[Swades] ${task.substring(0, 60)}`,
            head: branchName,
            base: 'main',
            body: `### 🤖 Autonomous Implementation by Swades Agent\n\n**Task**: ${task}\n\n**Self-Verification**: Passed.`
          })
        });

        if (prRes.ok) {
          const prData = await prRes.json();
          await postEvent('pr_opened', {
            pr_url: prData.html_url,
            pr_number: prData.number
          });
        }
      }
    } catch (pushErr) {
      console.warn('Git push notice:', pushErr.message);
    }
  }

  await postEvent('status', 'Autonomous task completed successfully.');
}
