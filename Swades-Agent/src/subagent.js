// ============================================================
// subagent.js — Isolated worktree subagent lifecycle + semaphore
// Worktrees now use OS temp directory instead of polluting project root
// ============================================================

import { exec } from "node:child_process";
import { resolve } from "node:path";
import { mkdir, rm } from "node:fs/promises";
import { existsSync } from "node:fs";
import { randomUUID } from "node:crypto";
import chalk from "chalk";
import { runAgent } from "./agent.js";
import { executeTool } from "./tools.js";
import { getWorktreeTempDir } from "./cleanup.js";

// ---- Concurrency Semaphore ----

export class Semaphore {
  constructor(max = 5) {
    this.max = max;
    this.active = 0;
    this.queue = [];
  }

  acquire() {
    return new Promise((resolve) => {
      if (this.active < this.max) {
        this.active++;
        resolve();
      } else {
        this.queue.push(resolve);
      }
    });
  }

  release() {
    this.active--;
    if (this.queue.length > 0) {
      this.active++;
      const next = this.queue.shift();
      next();
    }
  }
}

// Shared semaphore — caps parallel subagents at 5
const globalSemaphore = new Semaphore(5);

// ---- Shell helper ----

function shell(cmd, cwd) {
  return new Promise((resolve, reject) => {
    exec(cmd, { cwd, maxBuffer: 10 * 1024 * 1024, timeout: 120000 }, (err, stdout, stderr) => {
      if (err) return reject(new Error(stderr || stdout || err.message));
      resolve(stdout || "");
    });
  });
}

// ---- Worktree lifecycle (now uses OS temp directory) ----

/**
 * Create an isolated git worktree for a subagent.
 * Uses OS temp directory (/tmp/swades_worktrees/<project-hash>/) instead of
 * .swades_worktrees/ in the project root to keep the user's repo clean.
 *
 * Returns the absolute path to the worktree directory.
 */
async function createWorktree(label, baseDir) {
  const root = getWorktreeTempDir(baseDir);
  await mkdir(root, { recursive: true });

  const dirName = `${label.replace(/[^a-zA-Z0-9_-]/g, "_")}-${randomUUID().slice(0, 8)}`;
  const worktreePath = resolve(root, dirName);

  // Create a detached worktree from current HEAD
  await shell(`git worktree add --detach "${worktreePath}" HEAD`, baseDir);
  console.log(chalk.dim(`   📂 Worktree created: ${dirName} (in temp dir)`));
  return worktreePath;
}

/**
 * Capture the diff produced inside a worktree (vs HEAD).
 */
async function captureWorktreeDiff(worktreePath) {
  try {
    // Stage everything so diff picks up new files too
    await shell("git add -A", worktreePath);
    const diff = await shell("git diff --cached HEAD", worktreePath);
    return diff.trim();
  } catch (diffErr) {
    console.log(chalk.dim(`   ⚠ Diff capture failed: ${diffErr.message}`));
    return "";
  }
}

/**
 * Remove a worktree and clean up.
 * Handles both git worktree removal and force-cleanup on failure.
 */
async function removeWorktree(worktreePath, baseDir) {
  try {
    await shell(`git worktree remove --force "${worktreePath}"`, baseDir);
  } catch (removeErr) {
    console.log(chalk.dim(`   ⚠ git worktree remove failed: ${removeErr.message}, force-cleaning...`));
    // Force cleanup if git worktree remove fails
    try {
      await rm(worktreePath, { recursive: true, force: true });
      await shell("git worktree prune", baseDir);
    } catch (cleanupErr) {
      console.log(chalk.dim(`   ⚠ Force cleanup also failed: ${cleanupErr.message}`));
    }
  }
}

// ---- Subagent execution ----

/**
 * Run a single subagent in an isolated git worktree.
 *
 * @param {string} label       - Short identifier for this subtask
 * @param {string} description - Full task description for the agent
 * @param {string} baseDir     - Real workspace root (git repo)
 * @returns {{ label, diff, summary, success }}
 */
export async function runSubagent(label, description, baseDir) {
  await globalSemaphore.acquire();

  let worktreePath = null;
  try {
    console.log(chalk.cyan.bold(`\n🔹 Subagent [${label}] starting...`));
    worktreePath = await createWorktree(label, baseDir);

    // Override WORKDIR so all tools operate inside the worktree
    const prevWorkdir = process.env.WORKDIR;
    process.env.WORKDIR = worktreePath;

    // Run codebase indexer inside the worktree
    try {
      await executeTool("index_codebase", {});
    } catch (indexErr) {
      console.log(chalk.dim(`   ⚠ Subagent [${label}] index failed (non-fatal): ${indexErr.message}`));
    }

    // Run the ReAct agent — give it a generous but finite step budget per subtask
    const prefixedTask = `[SUBAGENT: ${label}]\n\n${description}\n\nYou are operating in an isolated workspace. Make all necessary changes to complete this subtask.`;
    const summary = await runAgent(prefixedTask, Infinity);

    // Capture the diff
    const diff = await captureWorktreeDiff(worktreePath);

    // Restore WORKDIR
    if (prevWorkdir !== undefined) process.env.WORKDIR = prevWorkdir;
    else delete process.env.WORKDIR;

    console.log(chalk.green(`   ✅ Subagent [${label}] complete (${diff.split("\n").length} diff lines)`));

    return { label, diff, summary: String(summary).slice(0, 1000), success: true };
  } catch (err) {
    console.log(chalk.red(`   ❌ Subagent [${label}] failed: ${err.message}`));
    return { label, diff: "", summary: err.message, success: false };
  } finally {
    // Teardown worktree
    if (worktreePath) {
      await removeWorktree(worktreePath, baseDir);
      console.log(chalk.dim(`   🗑️  Worktree [${label}] torn down`));
    }
    globalSemaphore.release();
  }
}

/**
 * Run multiple subagents in parallel (up to semaphore cap).
 * After all subagents complete, cleans up the temp worktree directory.
 *
 * @param {Array<{label, description}>} subtasks
 * @param {string} baseDir
 * @returns {Array<{label, diff, summary, success}>}
 */
export async function runSubagentsParallel(subtasks, baseDir) {
  console.log(chalk.cyan.bold(`\n🔷 Spawning ${subtasks.length} parallel subagents...`));
  const results = await Promise.all(
    subtasks.map(({ label, description }) => runSubagent(label, description, baseDir))
  );
  const passed = results.filter(r => r.success).length;
  console.log(chalk.cyan.bold(`\n🔷 All subagents complete: ${passed}/${results.length} succeeded`));

  // Auto-cleanup: prune temp worktree directory if empty
  const tempDir = getWorktreeTempDir(baseDir);
  if (existsSync(tempDir)) {
    try {
      await rm(tempDir, { recursive: true, force: true });
      console.log(chalk.dim(`   🧹 Cleaned up temp worktree directory`));
    } catch (cleanupErr) {
      console.log(chalk.dim(`   ⚠ Temp worktree cleanup failed: ${cleanupErr.message}`));
    }
  }

  // Prune any orphaned worktree references
  try {
    await shell("git worktree prune", baseDir);
  } catch (pruneErr) {
    console.log(chalk.dim(`   ⚠ git worktree prune failed: ${pruneErr.message}`));
  }

  return results;
}
