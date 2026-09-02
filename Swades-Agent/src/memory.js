// ============================================================
// memory.js — Persistent memory across sessions (isolated in cache dir)
// ============================================================

import { readFile, writeFile, mkdir } from "node:fs/promises";
import { resolve, dirname } from "node:path";
import chalk from "chalk";
import { getSwadesCacheDir } from "./cleanup.js";

/**
 * Get the memory file path, isolated in ~/.cache/swades/<project-hash>/
 * instead of polluting the project root.
 */
function getMemoryFilePath() {
  const workdir = process.env.WORKDIR || process.cwd();
  const cacheDir = getSwadesCacheDir(workdir);
  return resolve(cacheDir, "agent_memory.json");
}

/**
 * Load memory from disk. Returns { sessions: [], summary: "" }
 */
export async function loadMemory() {
  try {
    const memoryFile = getMemoryFilePath();
    const raw = await readFile(memoryFile, "utf-8");
    return JSON.parse(raw);
  } catch (err) {
    // Only log if it's not a simple "file doesn't exist" case
    if (err.code !== "ENOENT") {
      console.log(chalk.dim(`   ⚠ Memory load warning: ${err.message}`));
    }
    return { sessions: [], summary: "" };
  }
}

/**
 * Save memory to disk (in cache directory).
 */
export async function saveMemory(memory) {
  const memoryFile = getMemoryFilePath();
  await mkdir(dirname(memoryFile), { recursive: true });
  await writeFile(memoryFile, JSON.stringify(memory, null, 2), "utf-8");
}

/**
 * Record a completed session into memory.
 * Keeps the last 10 sessions to avoid unbounded growth.
 */
export async function recordSession(task, result, toolsUsed) {
  const memory = await loadMemory();

  memory.sessions.push({
    timestamp: new Date().toISOString(),
    task,
    result: result.slice(0, 500), // keep summaries short
    toolsUsed,
  });

  // Keep only last 10 sessions
  if (memory.sessions.length > 10) {
    memory.sessions = memory.sessions.slice(-10);
  }

  // Build a running summary of what the agent knows
  memory.summary = memory.sessions
    .map((s, i) => `[${i + 1}] ${s.timestamp}: "${s.task}" → ${s.result.slice(0, 100)}`)
    .join("\n");

  await saveMemory(memory);
  return memory;
}

/**
 * Build a memory context string to inject into the system prompt.
 */
export async function getMemoryContext() {
  const memory = await loadMemory();

  if (memory.sessions.length === 0) return "";

  let ctx = "\n\n## MEMORY — Previous Sessions\n";
  ctx += "You have memory of previous tasks you completed. Use this context to be more helpful:\n\n";

  for (const session of memory.sessions) {
    ctx += `- **${session.timestamp}**: Task: "${session.task}"\n`;
    ctx += `  Result: ${session.result.slice(0, 200)}\n`;
    if (session.toolsUsed?.length) {
      ctx += `  Tools used: ${session.toolsUsed.join(", ")}\n`;
    }
    ctx += "\n";
  }

  return ctx;
}
