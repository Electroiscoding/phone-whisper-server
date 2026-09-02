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

if (!jobId || !payloadPath) {
  console.error('Usage: node worker.js --job <id> --payload <payload_path>');
  process.exit(1);
}

const payload = JSON.parse(fs.readFileSync(payloadPath, 'utf8'));
const repoUrl = payload.repoUrl; // Assuming payload contains repoUrl

const workspaceDir = `/root/workspaces/${jobId}`;
const branchName = `swades/patch-${jobId}`;

async function postEvent(type, data) {
  try {
    await fetch('http://127.0.0.1:8080/v1/agent/internal_event', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ jobId, type, ...data })
    });
  } catch (err) {
    console.error('Failed to post event:', err);
  }
}

async function main() {
  await postEvent('status', { status: 'starting', message: `Job ${jobId} started.` });

  try {
    // Clone repo
    execSync(`mkdir -p /root/workspaces`);
    execSync(`git clone ${repoUrl} ${workspaceDir}`, { stdio: 'inherit' });
    
    // Config git and create branch
    execSync(`git config user.name "Swades Agent"`, { cwd: workspaceDir });
    execSync(`git config user.email "agent@swades.local"`, { cwd: workspaceDir });
    execSync(`git checkout -b ${branchName}`, { cwd: workspaceDir });

    await postEvent('status', { status: 'cloned', message: `Repo cloned and branched to ${branchName}.` });

    // Run agent
    await runAgent({
      jobId,
      workspaceDir,
      payload,
      postEvent
    });

    await postEvent('status', { status: 'completed', message: `Job ${jobId} finished successfully.` });
  } catch (err) {
    await postEvent('error', { error: err.message, stack: err.stack });
    console.error(err);
    process.exit(1);
  }
}

main();
