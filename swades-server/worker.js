import fs from 'fs';
import path from 'path';
import { execSync } from 'child_process';
import { parseGitHubUrl, cloneRepo, createBranch, configureGit, commitAll, pushBranch, openPullRequest, getDefaultBranch } from './github.js';
import { runAgent } from './agent.js';

function buildPRBody(result, task) {
  return `## 🤖 Swades Agent — Automated PR

**Task:** ${task || 'Automated code changes'}

### 📋 Summary:
${result.summary || 'Completed autonomous task execution.'}

### 📁 Files Changed:
${(result.filesChanged && result.filesChanged.length > 0) ? result.filesChanged.map(f => `- \`${f}\``).join('\n') : '- No files modified'}

**Total Reasoning Steps:** ${result.totalSteps || 1}

---
*Generated automatically by [Swades Agent](https://phone-whisper-server.pages.dev/#swades-studio) running on a self-hosted phone server.*`;
}

let eventQueue = [];
let isFlushing = false;

async function flushEvents() {
  if (isFlushing || eventQueue.length === 0) return;
  isFlushing = true;
  while (eventQueue.length > 0) {
    const item = eventQueue.shift();
    try {
      await fetch('http://127.0.0.1:8080/v1/agent/internal_event', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(item)
      });
    } catch (e) {}
  }
  isFlushing = false;
}

function sendInternalEvent(jobId, eventType, data, stepNumber = null) {
  eventQueue.push({
    job_id: jobId,
    type: eventType,
    data: data,
    step: stepNumber
  });
  flushEvents();
}

async function updateJobStatus(jobId, updates) {
  try {
    await fetch('http://127.0.0.1:8080/v1/agent/internal_event', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        job_id: jobId,
        updates: updates
      })
    });
  } catch (e) {}
}

async function checkForQueuedMessage(jobId) {
  try {
    const res = await fetch(`http://127.0.0.1:8080/v1/agent/pop_message/${jobId}`);
    if (res.ok) {
      const data = await res.json();
      if (data.has_message && data.next_message) {
        return data.next_message;
      }
    }
  } catch (e) {}
  return null;
}

async function main() {
  const args = process.argv.slice(2);
  const jobIdx = args.indexOf('--job');
  if (jobIdx === -1 || !args[jobIdx + 1]) {
    console.error('Error: --job <job_id> required');
    process.exit(1);
  }
  
  const jobId = args[jobIdx + 1];
  
  const homeDir = process.env.HOME || '/data/data/com.termux/files/home';
  const tempBase = path.join(homeDir, '.swades_scratch');
  const workspaceDir = path.join(tempBase, jobId, 'workspace');
  
  let job = null;
  if (process.env.JOB_PAYLOAD) {
    try {
      job = JSON.parse(process.env.JOB_PAYLOAD);
    } catch (e) {}
  }
  
  if (!job) {
    try {
      const res = await fetch(`http://127.0.0.1:8080/v1/agent/status/${jobId}`);
      if (res.ok) {
        job = await res.json();
      }
    } catch (e) {}
  }

  if (!job) {
    console.error(`Error: Job ${jobId} not found in RAM`);
    process.exit(1);
  }
  
  const githubPat = job.github_pat || job.github_token || null;
  const { owner, repo } = parseGitHubUrl(job.repo_url);
  const branchName = `swades/${jobId.slice(0, 8)}`;
  
  const onEvent = (event) => {
    sendInternalEvent(jobId, event.type, event.data, event.step_number || null);
  };
  
  try {
    // 1. CLONE & SETUP PHASE
    await updateJobStatus(jobId, { status: 'CLONING' });
    onEvent({ type: 'status', data: `Cloning ${owner}/${repo}...` });
    
    fs.mkdirSync(workspaceDir, { recursive: true });
    
    const cloneRes = cloneRepo(job.repo_url, workspaceDir, githubPat);
    if (!cloneRes.success) {
      throw new Error(`Clone failed: ${cloneRes.error}`);
    }
    
    configureGit(workspaceDir);
    const defaultBranch = await getDefaultBranch({ owner, repo, pat: githubPat });
    createBranch(workspaceDir, branchName);
    
    // 2. INTERACTIVE MULTI-TURN REASONING LOOP
    let currentTask = job.task;
    let allAccumulatedChanges = new Set();
    
    while (currentTask) {
      await updateJobStatus(jobId, { status: 'RUNNING', started_at: new Date().toISOString(), branch_name: branchName });
      onEvent({ type: 'status', data: `🚀 Agent active: "${currentTask}" (${job.model || 'qwen2.5'})` });
      
      const context = {
        workdir: workspaceDir,
        baseUrl: job.base_url || 'http://127.0.0.1:8080/v1',
        apiKey: job.api_key || 'local',
        model: job.model || 'qwen2.5',
        jobId,
        onEvent
      };
      
      const result = await runAgent(context, currentTask);
      
      if (result.filesChanged && result.filesChanged.length > 0) {
        result.filesChanged.forEach(f => allAccumulatedChanges.add(f));
      }
      
      // Check for Real Code Changes (Deterministic Heuristic)
      let hasRealCodeChanges = false;
      let actualModifiedFiles = [];
      try {
        const gitStatusOut = execSync('git status --porcelain', { cwd: workspaceDir, timeout: 30000 }).toString().trim();
        if (gitStatusOut) {
          actualModifiedFiles = gitStatusOut.split('\n').map(l => l.trim().split(/\s+/).slice(1).join(' ')).filter(Boolean);
          hasRealCodeChanges = actualModifiedFiles.length > 0;
        }
      } catch (e) {}

      // 3. DETERMINISTIC PR DECISION
      // PR is created IF AND ONLY IF:
      // a) The user is authenticated with GitHub (githubPat)
      // b) The AI model performed code modifications (hasRealCodeChanges && allAccumulatedChanges.size > 0)
      if (githubPat && hasRealCodeChanges && allAccumulatedChanges.size > 0) {
        onEvent({ type: 'status', data: `✨ ${actualModifiedFiles.length} modified files detected — creating Pull Request...` });
        commitAll(workspaceDir, `feat: ${currentTask.slice(0, 70)}`);
        pushBranch(workspaceDir, branchName, githubPat, job.repo_url);
        
        const pr = await openPullRequest({
          owner,
          repo,
          head: branchName,
          base: defaultBranch,
          title: `Swades Agent: ${currentTask.slice(0, 80)}`,
          body: buildPRBody(result, currentTask),
          pat: githubPat
        });
        
        if (pr.pr_url) {
          await updateJobStatus(jobId, {
            pr_url: pr.pr_url,
            pr_number: pr.pr_number,
            files_changed: JSON.stringify(Array.from(allAccumulatedChanges)),
            total_steps: result.totalSteps
          });
          onEvent({ type: 'complete', data: { pr_url: pr.pr_url, summary: result.summary, files_changed: Array.from(allAccumulatedChanges) } });
        } else {
          onEvent({ type: 'complete', data: { summary: result.summary, note: pr.error || 'Changes pushed to branch.' } });
        }
      } else {
        // Pure informational / analytical task (No PR created)
        onEvent({ type: 'status', data: 'ℹ️ No code files modified — completed analysis without Pull Request.' });
        onEvent({ type: 'complete', data: { summary: result.summary, note: 'Informational task completed (no PR required).' } });
      }

      // Check if user queued any follow-up messages while agent was working!
      const queuedMessage = await checkForQueuedMessage(jobId);
      if (queuedMessage) {
        onEvent({ type: 'status', data: `📥 Processing queued follow-up: "${queuedMessage}"` });
        currentTask = queuedMessage;
      } else {
        currentTask = null; // No more queued tasks, finish session
      }
    }
    
    await updateJobStatus(jobId, {
      status: 'COMPLETED',
      completed_at: new Date().toISOString()
    });
    
  } catch (err) {
    await updateJobStatus(jobId, { status: 'FAILED', error_message: err.message });
    onEvent({ type: 'error', data: { message: err.message } });
    console.error(`Job ${jobId} failed: ${err.message}`);
  } finally {
    // 🧹 EPHEMERAL PURGE: Erase all temporary clone files from disk immediately
    try {
      fs.rmSync(path.join(tempBase, jobId), { recursive: true, force: true });
    } catch (e) {}
  }
}

process.on('uncaughtException', async (err) => {
  console.error('Uncaught exception:', err);
  const args = process.argv.slice(2);
  const jobIdx = args.indexOf('--job');
  if (jobIdx !== -1 && args[jobIdx + 1]) {
    await updateJobStatus(args[jobIdx + 1], { status: 'FAILED', error_message: err.message });
  }
  process.exit(1);
});

main();
