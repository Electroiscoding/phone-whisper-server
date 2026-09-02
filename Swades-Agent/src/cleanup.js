// ============================================================
// cleanup.js — Workspace isolation & cache directory management
// ============================================================
// Moves all Swades internal files (.agent_index.json, .agent_memory.json,
// .agent_terminal.log) out of the user's project root and into
// ~/.cache/swades/<project-hash>/ to keep repositories clean.

import { createHash } from "node:crypto";
import { homedir, tmpdir } from "node:os";
import { resolve, basename } from "node:path";
import { mkdir, rm, rename, stat } from "node:fs/promises";
import { existsSync } from "node:fs";
import chalk from "chalk";

/**
 * Compute a deterministic cache directory for a given workspace path.
 * Uses a truncated SHA-256 hash to avoid path collisions.
 *
 * @param {string} workdir - Absolute path to the project workspace
 * @returns {string} - Absolute path to ~/.cache/swades/<project-hash>/
 */
export function getSwadesCacheDir(workdir) {
  const hash = createHash("sha256").update(workdir).digest("hex").slice(0, 16);
  const projectName = basename(workdir).replace(/[^a-zA-Z0-9_-]/g, "_");
  return resolve(homedir(), ".cache", "swades", `${projectName}-${hash}`);
}

/**
 * Get a path for temporary worktrees (uses OS temp directory).
 *
 * @param {string} workdir - Absolute workspace path
 * @returns {string} - Absolute path to /tmp/swades_worktrees/<project-hash>/
 */
export function getWorktreeTempDir(workdir) {
  const hash = createHash("sha256").update(workdir).digest("hex").slice(0, 16);
  const projectName = basename(workdir).replace(/[^a-zA-Z0-9_-]/g, "_");
  return resolve(tmpdir(), "swades_worktrees", `${projectName}-${hash}`);
}

/**
 * Ensure the cache directory exists, creating it if needed.
 *
 * @param {string} workdir - Absolute path to the project workspace
 * @returns {string} - The cache directory path (guaranteed to exist)
 */
export async function ensureCacheDir(workdir) {
  const cacheDir = getSwadesCacheDir(workdir);
  await mkdir(cacheDir, { recursive: true });
  return cacheDir;
}

/**
 * Migrate legacy files from the project root to the cache directory.
 * Silently skips files that don't exist. Prints a notice for each migrated file.
 *
 * Legacy files:
 *   - .agent_index.json
 *   - .agent_memory.json
 *   - .agent_terminal.log
 *
 * @param {string} workdir - Absolute path to the project workspace
 */
export async function migrateAndCleanup(workdir) {
  const cacheDir = await ensureCacheDir(workdir);

  const legacyFiles = [
    ".agent_index.json",
    ".agent_memory.json",
    ".agent_terminal.log",
  ];

  for (const filename of legacyFiles) {
    const oldPath = resolve(workdir, filename);
    const newPath = resolve(cacheDir, filename);

    if (existsSync(oldPath)) {
      try {
        // If the cache already has this file, just delete the legacy copy
        if (existsSync(newPath)) {
          await rm(oldPath, { force: true });
        } else {
          await rename(oldPath, newPath);
        }
        console.log(chalk.dim(`   🧹 Migrated ${filename} → ${cacheDir}/`));
      } catch (err) {
        console.log(chalk.dim(`   ⚠ Failed to migrate ${filename}: ${err.message}`));
      }
    }
  }

  // Clean up legacy .swades_worktrees/ directory if it exists in project root
  const legacyWorktreeDir = resolve(workdir, ".swades_worktrees");
  if (existsSync(legacyWorktreeDir)) {
    try {
      await rm(legacyWorktreeDir, { recursive: true, force: true });
      console.log(chalk.dim(`   🧹 Removed legacy .swades_worktrees/ from project root`));
    } catch (err) {
      console.log(chalk.dim(`   ⚠ Failed to remove .swades_worktrees/: ${err.message}`));
    }
  }
}
