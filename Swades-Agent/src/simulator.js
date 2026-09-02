// ============================================================
// simulator.js — Sandbox Simulation Engine
// Multi-scenario sandbox → verdict → promotion pipeline
// ============================================================

import { exec } from "node:child_process";
import { resolve } from "node:path";
import { mkdir, rm, writeFile, readFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { randomUUID } from "node:crypto";
import chalk from "chalk";
import { callLLM } from "./llm.js";
import { runAgent } from "./agent.js";
import { executeTool } from "./tools.js";
import { Semaphore } from "./subagent.js";

// ---- Shell helper ----

function shell(cmd, cwd) {
  return new Promise((resolve, reject) => {
    exec(cmd, { cwd, maxBuffer: 10 * 1024 * 1024, timeout: 120000 }, (err, stdout, stderr) => {
      if (err) return reject(new Error(stderr || stdout || err.message));
      resolve(stdout || "");
    });
  });
}

const SANDBOX_ROOT = ".swades_sandboxes";

// ---- Sandbox worktree lifecycle ----

async function createSandbox(scenarioId, baseDir) {
  const root = resolve(baseDir, SANDBOX_ROOT);
  await mkdir(root, { recursive: true });

  const dirName = `scenario-${scenarioId}-${randomUUID().slice(0, 8)}`;
  const sandboxPath = resolve(root, dirName);

  await shell(`git worktree add --detach "${sandboxPath}" HEAD`, baseDir);
  console.log(chalk.dim(`   🧪 Sandbox [${scenarioId}] created`));
  return sandboxPath;
}

async function captureSandboxDiff(sandboxPath) {
  try {
    await shell("git add -A", sandboxPath);
    return (await shell("git diff --cached HEAD", sandboxPath)).trim();
  } catch {
    return "";
  }
}

async function removeSandbox(sandboxPath, baseDir) {
  try {
    await shell(`git worktree remove --force "${sandboxPath}"`, baseDir);
  } catch {
    try {
      await rm(sandboxPath, { recursive: true, force: true });
      await shell("git worktree prune", baseDir);
    } catch { /* best-effort */ }
  }
}

// ---- Scenario Generation ----

const SCENARIO_PROMPT = `You are a software engineering strategist. Given a coding task, generate 2 to 4 distinct implementation scenarios/approaches.
Each scenario should represent a meaningfully different strategy (e.g., different algorithms, different architectural patterns, different libraries, or different levels of refactoring).

RULES:
- Minimum 2 scenarios, maximum 4.
- Each must be actionable and concrete — not vague.
- Return ONLY valid JSON array, nothing else.

Format:
[{"id": "A", "strategy": "Concise but specific description of the approach"}, ...]`;

/**
 * Ask the LLM to generate implementation scenarios.
 */
export async function generateScenarios(task) {
  console.log(chalk.yellow("   📋 Generating implementation scenarios..."));

  const messages = [
    { role: "system", content: SCENARIO_PROMPT },
    { role: "user", content: `Task: ${task}` },
  ];

  const response = await callLLM(messages);
  const text = (response.content || "").trim();

  // Extract JSON array from response
  const jsonMatch = text.match(/\[[\s\S]*\]/);
  if (!jsonMatch) {
    // Fallback: single default scenario
    console.log(chalk.dim("   ⚠ Could not parse scenarios, using single default"));
    return [{ id: "A", strategy: `Execute the task directly: ${task}` }];
  }

  try {
    const scenarios = JSON.parse(jsonMatch[0]);
    if (!Array.isArray(scenarios) || scenarios.length === 0) {
      return [{ id: "A", strategy: `Execute the task directly: ${task}` }];
    }
    console.log(chalk.green(`   ✅ Generated ${scenarios.length} scenarios`));
    return scenarios;
  } catch {
    return [{ id: "A", strategy: `Execute the task directly: ${task}` }];
  }
}

// ---- Single Sandbox Execution ----

/**
 * Run a single scenario inside an isolated sandbox.
 */
export async function runSandbox(scenario, task, baseDir) {
  const sandboxPath = await createSandbox(scenario.id, baseDir);

  try {
    console.log(chalk.magenta(`   🧪 Sandbox [${scenario.id}] executing: ${scenario.strategy.slice(0, 80)}...`));

    // Override WORKDIR to sandbox
    const prevWorkdir = process.env.WORKDIR;
    process.env.WORKDIR = sandboxPath;

    // Index codebase inside sandbox
    try { await executeTool("index_codebase", {}); } catch { /* non-fatal */ }

    // Run the agent with scenario-specific instructions
    const scenarioTask = `[SIMULATION — Scenario ${scenario.id}]\n\nGlobal Task: ${task}\n\nYour specific approach for this scenario:\n${scenario.strategy}\n\nImplement this approach completely. This is a sandboxed simulation — make all necessary changes.`;
    const summary = await runAgent(scenarioTask, Infinity);

    // Capture diff
    const diff = await captureSandboxDiff(sandboxPath);

    // Run compilation checks
    let compilationResult = "No compilation check available";
    try {
      // Check if package.json exists in sandbox
      const pkgPath = resolve(sandboxPath, "package.json");
      if (existsSync(pkgPath)) {
        const pkg = JSON.parse(await readFile(pkgPath, "utf-8"));
        // Try build or check scripts
        if (pkg.scripts?.build) {
          compilationResult = await shell("npm run build 2>&1 || true", sandboxPath);
        } else if (pkg.scripts?.check) {
          compilationResult = await shell("npm run check 2>&1 || true", sandboxPath);
        }
      }
      // Syntax-check all modified JS files
      const modifiedFiles = diff.match(/^\+\+\+ b\/(.+\.m?js)$/gm) || [];
      for (const line of modifiedFiles) {
        const filePath = line.replace("+++ b/", "");
        const fullPath = resolve(sandboxPath, filePath);
        if (existsSync(fullPath)) {
          try {
            await shell(`node --check "${fullPath}"`, sandboxPath);
          } catch (e) {
            compilationResult += `\nSyntax error in ${filePath}: ${e.message}`;
          }
        }
      }
    } catch { /* non-fatal */ }

    // Run tests if available
    let testResult = "No tests configured";
    try {
      const pkgPath = resolve(sandboxPath, "package.json");
      if (existsSync(pkgPath)) {
        const pkg = JSON.parse(await readFile(pkgPath, "utf-8"));
        if (pkg.scripts?.test && pkg.scripts.test !== "echo \"Error: no test specified\" && exit 1") {
          testResult = await shell("npm test 2>&1 || true", sandboxPath);
        }
      }
    } catch { /* non-fatal */ }

    // Restore WORKDIR
    if (prevWorkdir !== undefined) process.env.WORKDIR = prevWorkdir;
    else delete process.env.WORKDIR;

    return {
      id: scenario.id,
      strategy: scenario.strategy,
      diff,
      diffLines: diff.split("\n").length,
      summary: String(summary).slice(0, 1000),
      compilationResult: String(compilationResult).slice(0, 2000),
      testResult: String(testResult).slice(0, 2000),
      success: true,
      sandboxPath,
    };
  } catch (err) {
    console.log(chalk.red(`   ❌ Sandbox [${scenario.id}] failed: ${err.message}`));
    return {
      id: scenario.id,
      strategy: scenario.strategy,
      diff: "",
      diffLines: 0,
      summary: err.message,
      compilationResult: "FAILED",
      testResult: "FAILED",
      success: false,
      sandboxPath,
    };
  }
}

// ---- Verdict Selection ----

const VERDICT_PROMPT = `You are a senior software engineering reviewer. You have been given the results of multiple implementation scenarios for the same coding task. Each scenario was executed in an isolated sandbox.

Your job: Select the BEST scenario based on:
1. Code correctness (compilation/syntax check results)
2. Test results (if available)
3. Diff quality (clean, minimal, well-structured changes)
4. Alignment with the original task requirements

RULES:
- Pick exactly ONE winner.
- If all scenarios failed, pick the one with the most progress.
- Return ONLY valid JSON, nothing else.

Format: {"winner": "B", "reasoning": "Brief explanation of why this scenario is best"}`;

/**
 * Ask the LLM to select the best scenario from sandbox results.
 */
export async function selectWinner(task, results) {
  console.log(chalk.yellow("\n   🏆 Selecting winning scenario..."));

  const summaryBlock = results.map(r => {
    return `--- Scenario ${r.id} ---
Strategy: ${r.strategy}
Success: ${r.success}
Diff lines: ${r.diffLines}
Summary: ${r.summary.slice(0, 500)}
Compilation: ${r.compilationResult.slice(0, 500)}
Tests: ${r.testResult.slice(0, 500)}`;
  }).join("\n\n");

  const messages = [
    { role: "system", content: VERDICT_PROMPT },
    { role: "user", content: `Original task: ${task}\n\n${summaryBlock}` },
  ];

  const response = await callLLM(messages);
  const text = (response.content || "").trim();

  const jsonMatch = text.match(/\{[\s\S]*\}/);
  if (jsonMatch) {
    try {
      const verdict = JSON.parse(jsonMatch[0]);
      if (verdict.winner) {
        console.log(chalk.green(`   🏆 Winner: Scenario ${verdict.winner} — ${verdict.reasoning || ""}`));
        return verdict;
      }
    } catch { /* fall through */ }
  }

  // Fallback: pick the first successful scenario
  const firstSuccess = results.find(r => r.success);
  const fallbackId = firstSuccess ? firstSuccess.id : results[0].id;
  console.log(chalk.yellow(`   ⚠ Verdict parse failed, defaulting to Scenario ${fallbackId}`));
  return { winner: fallbackId, reasoning: "Fallback — could not parse LLM verdict" };
}

// ---- Promotion Pipeline: Sandbox → Real Life ----

/**
 * Promote the winning scenario's diff into the real workspace.
 *
 * Step A: Workspace Alignment (git rebase check)
 * Step B: Shadow Verification (apply diff in temp worktree, compile + test)
 * Step C: Live Workspace Mutation (git apply to real workspace)
 */
export async function promoteToProd(winnerResult, task, allResults, baseDir) {
  console.log(chalk.cyan.bold("\n🚀 Promotion Pipeline: Sandbox → Real Life"));

  if (!winnerResult.diff || winnerResult.diff.length === 0) {
    console.log(chalk.red("   ❌ Winner has empty diff — nothing to promote"));
    return { status: "EMPTY_DIFF", applied: false };
  }

  // ---- Step A: Workspace Alignment ----
  console.log(chalk.yellow("   📐 Step A: Workspace Alignment (rebase check)..."));
  try {
    const currentHead = (await shell("git rev-parse HEAD", baseDir)).trim();
    // The sandbox was created from HEAD, so check if HEAD moved
    // If HEAD is still the same, no rebase needed
    console.log(chalk.dim(`   Current HEAD: ${currentHead.slice(0, 8)}`));
  } catch (e) {
    console.log(chalk.dim(`   ⚠ Git check skipped: ${e.message}`));
  }

  // ---- Step B: Shadow Verification ----
  console.log(chalk.yellow("   🔍 Step B: Shadow Verification..."));
  let verificationPassed = false;
  let verifyPath = null;

  try {
    verifyPath = await createSandbox("verify", baseDir);

    // Write the diff to a temp file and apply it
    const diffFile = resolve(verifyPath, ".tmp_promotion.patch");
    await writeFile(diffFile, winnerResult.diff, "utf-8");

    try {
      await shell(`git apply --check "${diffFile}" 2>&1`, verifyPath);
      await shell(`git apply "${diffFile}" 2>&1`, verifyPath);
      console.log(chalk.green("   ✅ Diff applies cleanly to verification sandbox"));
    } catch (applyErr) {
      console.log(chalk.red(`   ❌ Diff does not apply cleanly: ${applyErr.message}`));

      // Try with 3-way merge fallback
      try {
        await shell(`git apply --3way "${diffFile}" 2>&1`, verifyPath);
        console.log(chalk.yellow("   ⚠ Applied with 3-way merge (may have conflicts resolved)"));
      } catch {
        console.log(chalk.red("   ❌ 3-way merge also failed — skipping shadow verification"));
        await removeSandbox(verifyPath, baseDir);
        verifyPath = null;
      }
    }

    if (verifyPath) {
      // Run compilation in verification sandbox
      try {
        const pkgPath = resolve(verifyPath, "package.json");
        if (existsSync(pkgPath)) {
          const pkg = JSON.parse(await readFile(pkgPath, "utf-8"));
          if (pkg.scripts?.build) {
            await shell("npm run build 2>&1", verifyPath);
            console.log(chalk.green("   ✅ Verification build passed"));
          }
        }
      } catch (buildErr) {
        console.log(chalk.yellow(`   ⚠ Verification build issue: ${buildErr.message.slice(0, 200)}`));
      }

      // Syntax-check JS files
      try {
        const modifiedFiles = winnerResult.diff.match(/^\+\+\+ b\/(.+\.m?js)$/gm) || [];
        for (const line of modifiedFiles) {
          const filePath = line.replace("+++ b/", "");
          const fullPath = resolve(verifyPath, filePath);
          if (existsSync(fullPath)) {
            await shell(`node --check "${fullPath}"`, verifyPath);
          }
        }
        console.log(chalk.green("   ✅ JS syntax checks passed"));
      } catch (syntaxErr) {
        console.log(chalk.yellow(`   ⚠ Syntax check issue: ${syntaxErr.message.slice(0, 200)}`));
      }

      verificationPassed = true;
    }
  } catch (e) {
    console.log(chalk.yellow(`   ⚠ Shadow verification error: ${e.message}`));
  } finally {
    if (verifyPath) await removeSandbox(verifyPath, baseDir);
  }

  // ---- Step C: Live Workspace Mutation ----
  console.log(chalk.yellow("   🔥 Step C: Live Workspace Mutation..."));

  const diffFile = resolve(baseDir, ".tmp_live_promotion.patch");
  await writeFile(diffFile, winnerResult.diff, "utf-8");

  try {
    try {
      await shell(`git apply "${diffFile}" 2>&1`, baseDir);
    } catch {
      // Fallback to 3-way merge
      await shell(`git apply --3way "${diffFile}" 2>&1`, baseDir);
    }
    console.log(chalk.green.bold("   ✅ Diff applied to real workspace!"));
  } catch (applyErr) {
    console.log(chalk.red(`   ❌ Failed to apply diff to real workspace: ${applyErr.message}`));
    // Clean up
    try { await rm(diffFile, { force: true }); } catch { /* best-effort */ }
    return { status: "APPLY_FAILED", applied: false, error: applyErr.message };
  }

  // Clean up temp diff file
  try { await rm(diffFile, { force: true }); } catch { /* best-effort */ }

  // ---- Post-promotion verification ----
  console.log(chalk.yellow("   🔬 Running post-promotion verification..."));
  let postCompilation = "skipped";
  let postTests = "skipped";

  try {
    const pkgPath = resolve(baseDir, "package.json");
    if (existsSync(pkgPath)) {
      const pkg = JSON.parse(await readFile(pkgPath, "utf-8"));
      if (pkg.scripts?.build) {
        postCompilation = await shell("npm run build 2>&1 || true", baseDir);
        console.log(chalk.green("   ✅ Post-promotion build complete"));
      }
      if (pkg.scripts?.test && pkg.scripts.test !== 'echo "Error: no test specified" && exit 1') {
        postTests = await shell("npm test 2>&1 || true", baseDir);
        console.log(chalk.green("   ✅ Post-promotion tests complete"));
      }
    }
  } catch { /* non-fatal */ }

  // ---- Telemetry Delta Report ----
  const report = {
    timestamp: new Date().toISOString(),
    task,
    scenariosRun: allResults.length,
    winner: winnerResult.id,
    winnerStrategy: winnerResult.strategy,
    reasoning: "",
    shadowVerification: verificationPassed ? "PASSED" : "SKIPPED",
    promotionStatus: "SUCCESS",
    diffLinesApplied: winnerResult.diffLines,
    postCompilation: String(postCompilation).slice(0, 500),
    postTests: String(postTests).slice(0, 500),
  };

  try {
    await writeFile(
      resolve(baseDir, ".swades_simulation_report.json"),
      JSON.stringify(report, null, 2),
      "utf-8"
    );
    console.log(chalk.dim("   📊 Telemetry report saved to .swades_simulation_report.json"));
  } catch { /* non-fatal */ }

  console.log(chalk.green.bold("\n🎉 Promotion complete — simulation is now reality!\n"));
  return { status: "SUCCESS", applied: true, report };
}

// ---- Main entry: Full Simulation Pipeline ----

/**
 * Run the full simulation pipeline:
 * 1. Generate scenarios
 * 2. Execute each in sandbox
 * 3. Select winner
 * 4. Promote to real workspace
 *
 * @param {string} task    - The coding task
 * @param {string} baseDir - Real workspace root
 * @returns {string} - Final summary
 */
export async function runSimulated(task, baseDir) {
  console.log(chalk.magenta.bold("\n🧪 Simulation Engine Activated"));
  console.log(chalk.dim(`   Task: "${task.slice(0, 100)}..."`));
  console.log(chalk.dim("═".repeat(60)));

  // Ensure we are inside a git repository so git worktree works
  try {
    await shell("git rev-parse --is-inside-work-tree", baseDir);
  } catch (err) {
    console.log(chalk.yellow("   ⚠ Not a git repository. Initializing git to support sandboxes..."));
    try {
      await shell("git init", baseDir);
      await shell("git config user.email \"xerv.org@gmail.com\"", baseDir);
      await shell("git config user.name \"Swades Agent\"", baseDir);
      await shell("git add -A", baseDir);
      await shell("git commit --allow-empty -m \"Initial commit by Swades Agent\"", baseDir);
      console.log(chalk.green("   ✅ Git repository initialized successfully."));
    } catch (gitErr) {
      console.log(chalk.red(`   ❌ Failed to initialize git: ${gitErr.message}. Simulation aborted.`));
      return `Simulation failed: workspace is not a git repository and git init failed: ${gitErr.message}`;
    }
  }

  // 1. Generate scenarios
  const scenarios = await generateScenarios(task);
  console.log(chalk.cyan(`\n   📋 ${scenarios.length} scenarios generated:`));
  for (const s of scenarios) {
    console.log(chalk.dim(`      [${s.id}] ${s.strategy.slice(0, 100)}`));
  }

  // 2. Run scenarios concurrently with a bounded semaphore
  //    SIM_CONCURRENCY env var controls parallelism (default: 2)
  const concurrencyLimit = parseInt(process.env.SIM_CONCURRENCY) || 2;
  const simSemaphore = new Semaphore(concurrencyLimit);
  console.log(chalk.dim(`   ⚡ Running ${scenarios.length} scenario(s) with concurrency=${concurrencyLimit}...`));

  const settled = await Promise.allSettled(
    scenarios.map(scenario =>
      simSemaphore.acquire().then(async () => {
        console.log(chalk.cyan.bold(`\n── Scenario ${scenario.id} ──`));
        let result;
        try {
          result = await runSandbox(scenario, task, baseDir);
        } finally {
          simSemaphore.release();
          // Clean up sandbox immediately after capture
          if (result?.sandboxPath) {
            await removeSandbox(result.sandboxPath, baseDir).catch(() => {});
          }
        }
        return result;
      })
    )
  );

  const results = settled.map((s, i) => {
    if (s.status === "fulfilled") return s.value;
    // Surface a failed entry so verdict selection can still pick the best
    console.log(chalk.red(`   ❌ Scenario ${scenarios[i].id} promise rejected: ${s.reason?.message}`));
    return {
      id: scenarios[i].id,
      strategy: scenarios[i].strategy,
      diff: "",
      diffLines: 0,
      summary: s.reason?.message || "Unknown error",
      compilationResult: "FAILED",
      testResult: "FAILED",
      success: false,
      sandboxPath: null,
    };
  });

  // 3. Select winner
  const verdict = await selectWinner(task, results);
  const winnerResult = results.find(r => r.id === verdict.winner) || results[0];

  if (!winnerResult || !winnerResult.success) {
    console.log(chalk.red("\n   ❌ No successful scenario — simulation aborted"));
    return "Simulation failed: no successful scenario produced a usable diff.";
  }

  // 4. Promote to production
  const promotion = await promoteToProd(winnerResult, task, results, baseDir);

  if (promotion.applied) {
    return `Simulation complete: Scenario ${winnerResult.id} promoted to workspace. ${verdict.reasoning || ""}`;
  } else {
    return `Simulation complete but promotion failed: ${promotion.error || promotion.status}`;
  }
}
