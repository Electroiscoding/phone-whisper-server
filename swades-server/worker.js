import fs from 'fs';
import path from 'path';
import { parseGitHubUrl, cloneRepo, createBranch, configureGit, commitAll, pushBranch, openPullRequest, getDefaultBranch } from './github.js';
import { runAgent } from './agent.js';

function buildPRBody(result) {
  return `## 🤖 Swades Agent — Automated Changes

**Task:** ${process.env.TASK_ORIG || 'Automated code change'}

**Summary:** ${result.summary}

**Files Changed:**
${result.filesChanged.map(f => `- ${f}`).join('\n') || '- No files modified'}

**Steps Taken:** ${result.totalSteps}

---
*This PR was generated automatically by [Swades Agent](https://phone-whisper-server.pages.dev/#swades-studio) running in-memory on a self-hosted Android phone.*`;
}

async function sendInternalEvent(jobId, eventType, data, stepNumber = null) {
  try {
    await fetch('http://127.0.0.1:8080/v1/agent/internal_event', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        job_id: jobId,
        type: eventType,
        data: data,
        step: stepNumber
      })
    });
  } catch (e) {}
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

async function main() {
  const args = process.argv.slice(2);
  const jobIdx = args.indexOf('--job');
  if (jobIdx === -1 || !args[jobIdx + 1]) {
    console.error('Error: --job <job_id> required');
    process.exit(1);
  }
  
  const jobId = args[jobIdx + 1];
  
  // Ephemeral scratch directory in /tmp (auto-cleaned)
  const tempBase = '/tmp/swades_scratch';
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
  
  process.env.TASK_ORIG = job.task;
  
  const onEvent = async (event) => {
    await sendInternalEvent(jobId, event.type, event.data, event.step_number || null);
  };
  
  try {
    // 1. CLONE PHASE
    await updateJobStatus(jobId, { status: 'CLONING' });
    await onEvent({ type: 'status', data: 'Cloning repository' });
    
    fs.mkdirSync(workspaceDir, { recursive: true });
    
    const cloneRes = cloneRepo(job.repo_url, workspaceDir, job.github_pat);
    if (!cloneRes.success) {
      throw new Error(`Clone failed: ${cloneRes.error}`);
    }
    
    configureGit(workspaceDir);
    const { owner, repo } = parseGitHubUrl(job.repo_url);
    const defaultBranch = await getDefaultBranch({ owner, repo, pat: job.github_pat });
    
    const branchName = `swades/${jobId.slice(0, 8)}`;
    createBranch(workspaceDir, branchName);
    
    // 2. AGENT PHASE
    await updateJobStatus(jobId, { status: 'RUNNING', started_at: new Date().toISOString() });
    await onEvent({ type: 'status', data: 'Agent running in-memory' });
    
    const context = {
      workdir: workspaceDir,
      baseUrl: job.base_url || 'http://127.0.0.1:8080/v1',
      apiKey: job.api_key || 'local',
      model: job.model || 'qwen2.5',
      jobId,
      onEvent
    };
    
    const result = await runAgent(context, job.task);
    
    // 3. PR PHASE
    await onEvent({ type: 'status', data: 'Creating PR' });
    commitAll(workspaceDir, 'feat: ' + job.task.slice(0, 72));
    pushBranch(workspaceDir, branchName, job.github_pat, job.repo_url);
    
    const pr = await openPullRequest({
      owner,
      repo,
      head: branchName,
      base: defaultBranch,
      title: 'Swades Agent: ' + job.task.slice(0, 100),
      body: buildPRBody(result),
      pat: job.github_pat
    });
    
    await updateJobStatus(jobId, {
      status: 'COMPLETED',
      completed_at: new Date().toISOString(),
      pr_url: pr.pr_url,
      pr_number: pr.pr_number,
      files_changed: JSON.stringify(result.filesChanged),
      total_steps: result.totalSteps
    });
    
    await onEvent({ type: 'complete', data: { pr_url: pr.pr_url, summary: result.summary } });
    console.log(`Job ${jobId} completed successfully. PR: ${pr.pr_url}`);
    
  } catch (err) {
    await updateJobStatus(jobId, { status: 'FAILED', error_message: err.message });
    await onEvent({ type: 'error', data: { message: err.message } });
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
