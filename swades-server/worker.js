import fs from 'fs';
import path from 'path';
import { parseGitHubUrl, cloneRepo, createBranch, configureGit, commitAll, pushBranch, openPullRequest, getDefaultBranch } from './github.js';
import { runAgent } from './agent.js';

function buildPRBody(result, task) {
  return `## 🤖 Swades Agent — Automated PR

**Task:** ${task || 'Automated code changes'}

### 📋 Summary:
${result.summary || 'Completed autonomous task execution.'}

### 📁 Files Changed:
${(result.filesChanged && result.filesChanged.length > 0) ? result.filesChanged.map(f => `- \`${f}\``).join('\n') : '- `SWADES_REPORT.md` (Analysis Report)'}

**Total Reasoning Steps:** ${result.totalSteps || 1}

---
*Generated automatically by [Swades Agent](https://phone-whisper-server.pages.dev/#swades-studio) running on a self-hosted phone server.*`;
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
  process.env.TASK_ORIG = job.task;
  
  const onEvent = async (event) => {
    await sendInternalEvent(jobId, event.type, event.data, event.step_number || null);
  };
  
  try {
    // 1. CLONE PHASE
    await updateJobStatus(jobId, { status: 'CLONING' });
    await onEvent({ type: 'status', data: 'Cloning repository' });
    
    fs.mkdirSync(workspaceDir, { recursive: true });
    
    const cloneRes = cloneRepo(job.repo_url, workspaceDir, githubPat);
    if (!cloneRes.success) {
      throw new Error(`Clone failed: ${cloneRes.error}`);
    }
    
    configureGit(workspaceDir);
    const { owner, repo } = parseGitHubUrl(job.repo_url);
    const defaultBranch = await getDefaultBranch({ owner, repo, pat: githubPat });
    
    const branchName = `swades/${jobId.slice(0, 8)}`;
    createBranch(workspaceDir, branchName);
    
    // 2. AGENT PHASE
    await updateJobStatus(jobId, { status: 'RUNNING', started_at: new Date().toISOString(), branch_name: branchName });
    await onEvent({ type: 'status', data: `Agent running in-memory (${job.model || 'qwen2.5'})` });
    
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
    if (githubPat) {
      await onEvent({ type: 'status', data: 'Pushing changes to GitHub branch' });
      
      // If no files modified, create a report file
      if (!result.filesChanged || result.filesChanged.length === 0) {
        const reportPath = path.join(workspaceDir, 'SWADES_REPORT.md');
        fs.writeFileSync(reportPath, `# 🤖 Swades Agent Report\n\n**Task:** ${job.task}\n\n## Findings & Summary\n\n${result.summary || 'Task completed successfully.'}\n`, 'utf8');
        result.filesChanged = ['SWADES_REPORT.md'];
      }
      
      commitAll(workspaceDir, `feat(swades): ${job.task.slice(0, 70)}`);
      
      const pushRes = pushBranch(workspaceDir, branchName, githubPat, job.repo_url);
      if (!pushRes.success) {
        await onEvent({ type: 'status', data: `⚠️ Git push note: ${pushRes.error}` });
      }
      
      await onEvent({ type: 'status', data: 'Opening GitHub Pull Request' });
      const pr = await openPullRequest({
        owner,
        repo,
        head: branchName,
        base: defaultBranch,
        title: `Swades Agent: ${job.task.slice(0, 80)}`,
        body: buildPRBody(result, job.task),
        pat: githubPat
      });
      
      if (pr.pr_url) {
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
      } else {
        await updateJobStatus(jobId, {
          status: 'COMPLETED',
          completed_at: new Date().toISOString(),
          files_changed: JSON.stringify(result.filesChanged),
          total_steps: result.totalSteps
        });
        await onEvent({ type: 'complete', data: { summary: result.summary, note: pr.error || 'No PR created (check permissions)' } });
      }
    } else {
      await updateJobStatus(jobId, {
        status: 'COMPLETED',
        completed_at: new Date().toISOString(),
        files_changed: JSON.stringify(result.filesChanged),
        total_steps: result.totalSteps
      });
      await onEvent({ type: 'complete', data: { summary: result.summary, note: 'Login with GitHub to enable automatic Pull Requests.' } });
    }
    
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
