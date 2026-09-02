// ============================================================
// orchestrator.js — Task complexity evaluation + subagent
// spawning + simulation integration
// ============================================================

import chalk from "chalk";
import { exec } from "node:child_process";
import { resolve } from "node:path";
import { writeFile, readFile, mkdir, rm } from "node:fs/promises";
import { existsSync } from "node:fs";
import { callLLM } from "./llm.js";
import { runSubagent, runSubagentsParallel } from "./subagent.js";
import { runSimulated } from "./simulator.js";

// ---- Shell helper ----

function shell(cmd, cwd) {
  return new Promise((resolve, reject) => {
    exec(cmd, { cwd, maxBuffer: 10 * 1024 * 1024, timeout: 120000 }, (err, stdout, stderr) => {
      if (err) return reject(new Error(stderr || stdout || err.message));
      resolve(stdout || "");
    });
  });
}

// ---- Complexity Evaluation ----

const CLASSIFIER_PROMPT = `You are a task complexity classifier for an AI coding agent. Given a coding task, classify it.

LOW complexity — Execute directly in a single agent thread:
- Single-file edits, documentation updates, simple bug fixes
- Config changes, renaming, formatting
- Anything sequential that does not benefit from parallelism

HIGH complexity — Requires parallel subagents + simulation:
- Multi-file refactors spanning 3+ files
- Full feature implementations (frontend + backend + tests)
- Architectural changes, large-scale rewrites
- Tasks where multiple valid approaches exist and simulation would help pick the best

RULES:
- Be conservative: if in doubt, classify as LOW.
- For HIGH complexity, decompose into 2-5 concrete subtasks.
- Each subtask must be independently executable in an isolated workspace.
- Return ONLY valid JSON, nothing else.

LOW format:  {"level": "LOW"}
HIGH format: {"level": "HIGH", "subtasks": [{"label": "short-name", "description": "what to do"}, ...]}`;

/**
 * Evaluate task complexity using LLM classification.
 *
 * @param {string} task - The coding task
 * @returns {{ level: "LOW"|"HIGH", subtasks: Array<{label, description}> }}
 */
export async function evaluateComplexity(task) {
  console.log(chalk.dim("   🧠 Evaluating task complexity..."));

  let systemPrompt = CLASSIFIER_PROMPT;
  if (process.env.SUBAGENTS_ONLY === "true") {
    systemPrompt += "\n\nCRITICAL: The user has explicitly enabled subagents-only execution. You MUST classify this task as HIGH complexity and decompose it into 2-5 concrete subtasks.";
  }

  const messages = [
    { role: "system", content: systemPrompt },
    { role: "user", content: `Task: ${task}` },
  ];

  try {
    const response = await callLLM(messages);
    const text = (response.content || "").trim();

    const jsonMatch = text.match(/\{[\s\S]*\}/);
    if (jsonMatch) {
      const result = JSON.parse(jsonMatch[0]);
      if (result.level === "HIGH" && Array.isArray(result.subtasks) && result.subtasks.length > 0) {
        console.log(chalk.cyan(`   🧠 Complexity: HIGH (${result.subtasks.length} subtasks)`));
        return result;
      }
      console.log(chalk.dim("   🧠 Complexity: LOW"));
      return { level: "LOW", subtasks: [] };
    }
  } catch (e) {
    console.log(chalk.dim(`   ⚠ Complexity eval failed: ${e.message}, defaulting to LOW`));
  }

  return { level: "LOW", subtasks: [] };
}

// ---- Diff Merge Engine ----

/**
 * Merge multiple subagent diffs into the real workspace.
 * Uses git apply with 3-way merge fallback.
 * For conflicts, spawns a merge-resolution subagent.
 */
export async function mergeDiffs(results, baseDir) {
  console.log(chalk.cyan.bold("\n🔗 Merging subagent artifacts into real workspace..."));

  const successfulResults = results.filter(r => r.success && r.diff.length > 0);
  if (successfulResults.length === 0) {
    console.log(chalk.yellow("   ⚠ No diffs to merge"));
    return { merged: 0, failed: 0, conflicts: [] };
  }

  let merged = 0;
  let failed = 0;
  const conflicts = [];

  for (const result of successfulResults) {
    const diffFile = resolve(baseDir, `.tmp_merge_${result.label}.patch`);
    await writeFile(diffFile, result.diff, "utf-8");

    try {
      // Try clean apply first
      try {
        await shell(`git apply --check "${diffFile}" 2>&1`, baseDir);
        await shell(`git apply "${diffFile}" 2>&1`, baseDir);
        console.log(chalk.green(`   ✅ [${result.label}] merged cleanly`));
        merged++;
      } catch (applyErr) {
        console.log(chalk.dim(`   ⚠ Clean apply failed for [${result.label}]: ${applyErr.message}`));
        // Fallback to 3-way merge
        try {
          await shell(`git apply --3way "${diffFile}" 2>&1`, baseDir);
          console.log(chalk.yellow(`   ⚠ [${result.label}] merged with 3-way (may need review)`));
          merged++;
        } catch (mergeErr) {
          console.log(chalk.red(`   ❌ [${result.label}] conflict — queuing resolution`));
          conflicts.push({ label: result.label, diff: result.diff, error: mergeErr.message });
          failed++;
        }
      }
    } finally {
      try { await rm(diffFile, { force: true }); } catch (rmErr) { console.log(chalk.dim(`   ⚠ Patch file cleanup failed: ${rmErr.message}`)); }
    }
  }

  // Handle conflicts with a merge-resolution subagent
  if (conflicts.length > 0) {
    console.log(chalk.yellow(`\n   🔧 Spawning merge-resolution subagent for ${conflicts.length} conflict(s)...`));
    for (const conflict of conflicts) {
      const mergeTask = `A git merge conflict occurred while applying changes from subagent "${conflict.label}".

The diff that failed to apply:
\`\`\`diff
${conflict.diff.slice(0, 5000)}
\`\`\`

Error: ${conflict.error}

Your job: Manually apply the intended changes from this diff to the current codebase. Read the relevant files, understand the intent of the diff, and use patch_file to apply the changes correctly. Resolve any conflicts.`;

      try {
        await runSubagent(`merge-${conflict.label}`, mergeTask, baseDir);
        merged++;
        failed--;
      } catch (mergeResErr) {
        console.log(chalk.red(`   ❌ Merge resolution for [${conflict.label}] also failed: ${mergeResErr.message}`));
      }
    }
  }

  console.log(chalk.cyan(`   🔗 Merge complete: ${merged} applied, ${failed} failed`));
  return { merged, failed, conflicts };
}

// ---- Main Orchestrated Execution ----

/**
 * Run the full orchestrated pipeline:
 * 1. Evaluate complexity
 * 2. If LOW → return null (caller runs normal agent)
 * 3. If HIGH → spawn subagents in parallel → merge diffs
 *    Then run simulation on the merged state for final verification
 *
 * @param {string} task    - The coding task
 * @param {string} baseDir - Real workspace root
 * @returns {string|null}  - Result string, or null if LOW complexity
 */
export async function runOrchestrated(task, baseDir) {
  const evaluation = await evaluateComplexity(task);

  // --sim flag: force full pipeline even if classifier says LOW
  const forceOrchestrated = process.env.FORCE_ORCHESTRATED === "true";

  if (evaluation.level === "LOW" && !forceOrchestrated) {
    return null; // Signal to caller: run normal single-agent
  }

  // If forced on a LOW task, synthesize a minimal single-subtask decomposition
  if (evaluation.level === "LOW" && forceOrchestrated) {
    console.log(chalk.yellow("   ⚡ Complexity: LOW but --sim flag forces orchestrated pipeline"));
    evaluation.level = "HIGH";
    evaluation.subtasks = [{ label: "main", description: task }];
  }

  console.log(chalk.green.bold("\n🔷 Orchestrated Execution Activated"));
  console.log(chalk.dim(`   Task: "${task.slice(0, 100)}"`));
  console.log(chalk.dim(`   Subtasks: ${evaluation.subtasks.length}`));
  console.log(chalk.dim("═".repeat(60)));

  // Ensure we are inside a git repository so git worktree works
  try {
    await shell("git rev-parse --is-inside-work-tree", baseDir);
  } catch (err) {
    console.log(chalk.yellow("   ⚠ Not a git repository. Initializing git to support subagents and sandboxes..."));
    try {
      await shell("git init", baseDir);
      await shell("git config user.email \"xerv.org@gmail.com\"", baseDir);
      await shell("git config user.name \"Swades Agent\"", baseDir);
      await shell("git add -A", baseDir);
      await shell("git commit --allow-empty -m \"Initial commit by Swades Agent\"", baseDir);
      console.log(chalk.green("   ✅ Git repository initialized successfully."));
    } catch (gitErr) {
      console.log(chalk.red(`   ❌ Failed to initialize git: ${gitErr.message}. Falling back to single-agent mode.`));
      return null;
    }
  }

  // Phase 1: Run subagents in parallel
  const subagentResults = await runSubagentsParallel(evaluation.subtasks, baseDir);

  // Phase 2: Merge diffs into workspace
  const mergeResult = await mergeDiffs(subagentResults, baseDir);

  // Phase 3: Run simulation on the merged state to verify and optimize
  if (process.env.SUBAGENTS_ONLY === "true") {
    console.log(chalk.cyan.bold("\n🧪 Post-merge simulation skipped (Subagents-only mode enabled)."));
    const summary = [
      `🔷 Orchestrated execution complete.`,
      `   Subagents: ${subagentResults.length} spawned, ${subagentResults.filter(r => r.success).length} succeeded`,
      `   Merge: ${mergeResult.merged} applied, ${mergeResult.failed} failed`,
      `   Simulation: (skipped)`,
    ].join("\n");
    console.log(chalk.green.bold("\n" + summary + "\n"));
    return summary;
  }

  console.log(chalk.cyan.bold("\n🧪 Post-merge simulation for verification & optimization..."));
  const verificationTask = `Verify and optimize the following changes that were just applied to the codebase:

Original task: ${task}

Subagent results:
${subagentResults.map(r => `- [${r.label}] ${r.success ? "SUCCESS" : "FAILED"}: ${r.summary.slice(0, 200)}`).join("\n")}

Merge result: ${mergeResult.merged} merged, ${mergeResult.failed} failed

Your job: Review the current state of the codebase. Fix any integration issues between the merged subagent outputs. Run any available tests. Ensure everything compiles and works together coherently.`;

  const simResult = await runSimulated(verificationTask, baseDir);

  // Build summary
  const summary = [
    `🔷 Orchestrated execution complete.`,
    `   Subagents: ${subagentResults.length} spawned, ${subagentResults.filter(r => r.success).length} succeeded`,
    `   Merge: ${mergeResult.merged} applied, ${mergeResult.failed} failed`,
    `   Simulation: ${simResult}`,
  ].join("\n");

  console.log(chalk.green.bold("\n" + summary + "\n"));
  return summary;
}
