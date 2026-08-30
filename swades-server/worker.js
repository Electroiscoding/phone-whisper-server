import fs from 'fs';
import path from 'path';
import { initDatabase, getJob, updateJob, appendLog } from './job.js';
import { parseGitHubUrl, cloneRepo, createBranch, configureGit, commitAll, pushBranch, openPullRequest, getDefaultBranch } from './github.js';
import { runAgent } from './agent.js';

function buildPRBody(result) {
  return `## 🤖 Swades Agent — Automated Changes

**Task:** ${process.env.TASK_ORIG || 'Automated code change'}

**Summary:** ${result.summary}

**Files Changed:**
${result.filesChanged.map(f => `- ${f}`).join('\\n') || '- No files modified'}

**Steps Taken:** ${result.totalSteps}

---
*This PR was generated automatically by [Swades Agent](https://phone-whisper-server.pages.dev/#swades-studio) running on a self-hosted Android phone.*`;
}

async function main() {
  const args = process.argv.slice(2);
  const jobIdx = args.indexOf('--job');
  if (jobIdx === -1 || !args[jobIdx + 1]) {
    console.error('Error: --job <job_id> required');
    process.exit(1);
  }
  
  const jobId = args[jobIdx + 1];
  initDatabase();
  
  const job = getJob(jobId);
  if (!job || job.status !== 'QUEUED') {
    console.error(`Error: Job ${jobId} not found or not QUEUED`);
    process.exit(1);
  }
  
  process.env.TASK_ORIG = job.task;
  const workspaceDir = `/tmp/swades_jobs/${jobId}/workspace`;
  const logFile = `/tmp/swades_jobs/${jobId}/agent.log`;
  
  const onEvent = (event) => {
    appendLog(jobId, event.type, event.data, event.step_number || null);
    fs.appendFileSync(logFile, JSON.stringify({ ...event, timestamp: event.timestamp || new Date().toISOString() }) + '\\n', 'utf8');
  };
  
  try {
    // CLONE PHASE
    updateJob(jobId, { status: 'CLONING' });
    onEvent({ type: 'status', data: 'Cloning repository' });
    
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
    
    // AGENT PHASE
    updateJob(jobId, { status: 'RUNNING', started_at: new Date().toISOString() });
    onEvent({ type: 'status', data: 'Agent running' });
    
    const context = {
      workdir: workspaceDir,
      baseUrl: job.base_url,
      apiKey: job.api_key_hash, // Pass hash or logic to retrieve real key if needed
      model: job.model,
      jobId,
      onEvent
    };
    
    const result = await runAgent(context, job.task);
    
    // PR PHASE
    onEvent({ type: 'status', data: 'Creating PR' });
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
    
    updateJob(jobId, {
      status: 'COMPLETED',
      completed_at: new Date().toISOString(),
      pr_url: pr.pr_url,
      pr_number: pr.pr_number,
      files_changed: JSON.stringify(result.filesChanged),
      total_steps: result.totalSteps
    });
    
    onEvent({ type: 'complete', data: { pr_url: pr.pr_url } });
    console.log(`Job ${jobId} completed successfully. PR: ${pr.pr_url}`);
    
  } catch (err) {
    updateJob(jobId, { status: 'FAILED', error_message: err.message });
    onEvent({ type: 'error', data: { message: err.message } });
    console.error(`Job ${jobId} failed: ${err.message}`);
    process.exit(1);
  }
}

process.on('uncaughtException', (err) => {
  console.error('Uncaught exception:', err);
  const args = process.argv.slice(2);
  const jobIdx = args.indexOf('--job');
  if (jobIdx !== -1 && args[jobIdx + 1]) {
    updateJob(args[jobIdx + 1], { status: 'FAILED', error_message: err.message });
  }
  process.exit(1);
});

main();
