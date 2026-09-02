import fs from 'fs';
import path from 'path';
import { execSync } from 'child_process';
import { runAgent } from './src/agent.js';

// Parse args
const args = process.argv.slice(2);
let jobId = null;
let payloadPath = null;

for (let i = 0; i < args.length; i++) {
  if (args[i] === '--job') jobId = args[++i];
  else if (args[i] === '--payload') payloadPath = args[++i];
}

if (!jobId && process.env.JOB_ID) {
  jobId = process.env.JOB_ID;
}

if (!jobId) {
  console.error('Usage: node worker.js --job <id> [--payload <payload_path>]');
  process.exit(1);
}

// Resolve payload
let payload = null;
if (process.env.JOB_PAYLOAD) {
  try { payload = JSON.parse(process.env.JOB_PAYLOAD); } catch(e) {}
}
if (!payload && payloadPath && fs.existsSync(payloadPath)) {
  try { payload = JSON.parse(fs.readFileSync(payloadPath, 'utf8')); } catch(e) {}
}

async function postEvent(type, data) {
  try {
    await fetch('http://127.0.0.1:8080/v1/agent/internal_event', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        job_id: jobId, 
        jobId, 
        type, 
        data, 
        updates: type === 'pr_opened' ? { pr_url: data?.pr_url, status: 'COMPLETED' } : (type === 'status' && String(data).includes('completed') ? { status: 'COMPLETED' } : undefined)
      })
    });
  } catch (err) {
    console.error('Failed to post event:', err);
  }
}

async function main() {
  if (!payload) {
    try {
      const res = await fetch(`http://127.0.0.1:8080/v1/agent/status/${jobId}`);
      if (res.ok) payload = await res.json();
    } catch(e) {}
  }

  if (!payload) {
    await postEvent('error', { error: 'Job payload not found' });
    process.exit(1);
  }

  const repoUrl = payload.repo_url || payload.repoUrl;
  const task = payload.task || 'Analyze repository';
  const token = payload.github_token || payload.github_pat;

  await postEvent('status', `Initializing workspace for task: ${task}`);

  const workspaceDir = `/root/workspaces/${jobId}`;
  const branchName = `swades/patch-${jobId}`;

  try {
    execSync(`mkdir -p /root/workspaces`);
    
    // Auth clone URL
    let cloneUrl = repoUrl;
    if (token && cloneUrl.startsWith('https://github.com/')) {
      cloneUrl = cloneUrl.replace('https://github.com/', `https://${token}@github.com/`);
    }

    await postEvent('status', `Cloning repository: ${repoUrl.replace(/^https:\/\/github\.com\//, '')}`);
    execSync(`rm -rf ${workspaceDir}`);
    execSync(`git clone ${cloneUrl} ${workspaceDir}`, { stdio: 'pipe' });
    
    // Config git and create branch
    execSync(`git config user.name "Swades Agent"`, { cwd: workspaceDir });
    execSync(`git config user.email "agent@swades.local"`, { cwd: workspaceDir });
    execSync(`git checkout -b ${branchName}`, { cwd: workspaceDir });

    await postEvent('status', `Created working branch: ${branchName}`);

    // Run agent
    await runAgent({
      jobId,
      workspaceDir,
      payload,
      postEvent
    });

    await postEvent('status', `Autonomous task completed successfully.`);
  } catch (err) {
    await postEvent('error', { error: err.message, stack: err.stack });
    console.error('Worker execution error:', err);
    process.exit(1);
  }
}

main();
