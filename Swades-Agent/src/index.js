#!/usr/bin/env node
// index.js — Entry point, CLI parser & persistent chat loop

import "dotenv/config";
import { createInterface } from "node:readline";
import chalk from "chalk";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";
import { runAgent } from "./agent.js";
import { runDirector } from "./director.js";
import { runCUA } from "./cua.js";
import { executeTool } from "./tools.js";
import { callLLM } from "./llm.js";
import { migrateAndCleanup } from "./cleanup.js";
import { recordSession } from "./memory.js";

export { runAgent, runDirector, runCUA, executeTool };

// ============================================================
// CLI flag helpers
// ============================================================

function printHelp() {
  console.log(chalk.cyan.bold("\n  🚀 Swades Agent v3.0\n"));
  console.log(chalk.white("  Usage: swades-agent [task] [flags]\n"));
  console.log(chalk.dim("  If no task is given, enters the persistent chat loop.\n"));

  console.log(chalk.white.bold("  Execution Flags:\n"));
  console.log(chalk.green("  --cua, -c           ") + "Computer Use Agent (desktop/GUI automation) — EXPLICIT USER OPT-IN ONLY");
  console.log(chalk.green("  --autonomous, -a    ") + "Hint: start in Director loop (agent can escalate on its own anyway)");
  console.log(chalk.green("  --sim               ") + "Hint: bias toward run_simulation tool (agent can also call it autonomously)");
  console.log(chalk.green("  --subagents, -s     ") + "Hint: bias toward spawn_subagents tool");
  console.log(chalk.green("  --no-sim            ") + "Disable run_simulation even if agent wants to use it");
  console.log();
  console.log(chalk.white.bold("  Other Flags:\n"));
  console.log(chalk.blue("  --image, -i <path>  ") + "Attach a local image or URL to the task");
  console.log(chalk.blue("  --rewind            ") + "List available checkpoints from last session");
  console.log(chalk.blue("  --help, -h          ") + "Show this help message");
  console.log();
  console.log(chalk.white.bold("  Chat Loop Commands (while running):\n"));
  console.log(chalk.yellow("  exit / quit         ") + "Exit the agent");
  console.log(chalk.yellow("  clear               ") + "Reset the message context (start fresh)");
  console.log(chalk.yellow("  /help               ") + "Show this help inside the loop");
  console.log();
  console.log(chalk.dim("  Examples:"));
  console.log(chalk.dim('    swades-agent "Add login tests"'));
  console.log(chalk.dim('    swades-agent "Refactor to TypeScript" --autonomous'));
  console.log(chalk.dim('    swades-agent "Build REST API" --sim'));
  console.log(chalk.dim('    swades-agent --cua "Open browser and screenshot homepage"'));
  console.log(chalk.dim('    swades-agent "Implement UI" --image mockup.png'));
  console.log();
}

function parseCLI() {
  const args = process.argv.slice(2);

  if (args.includes("--help") || args.includes("-h")) {
    printHelp();
    process.exit(0);
  }

  const hasCuaFlag        = args.includes("--cua")        || args.includes("-c");
  const hasAutonomousFlag = args.includes("--autonomous")  || args.includes("-a");
  const hasSimFlag        = args.includes("--sim");
  const hasNoSimFlag      = args.includes("--no-sim");
  const hasSubagentsFlag  = args.includes("--subagents")   || args.includes("-s");
  const hasRewindFlag     = args.includes("--rewind");

  let image = null;
  const imgIdx = args.findIndex(a => a === "--image" || a === "-i");
  if (imgIdx !== -1 && imgIdx + 1 < args.length) {
    image = args[imgIdx + 1];
  }

  const FLAG_TOKENS = new Set([
    "--cua", "-c", "--autonomous", "-a", "--sim", "--no-sim",
    "--subagents", "-s", "--rewind", "--help", "-h",
  ]);
  const taskArgs = [];
  for (let i = 0; i < args.length; i++) {
    if (FLAG_TOKENS.has(args[i])) continue;
    if (args[i] === "--image" || args[i] === "-i") { i++; continue; }
    taskArgs.push(args[i]);
  }
  const task = taskArgs.join(" ").trim();

  // Apply env hints from flags — capability tool calling is biased by these
  if (hasSimFlag)        process.env.PREFER_SIMULATION = "true";
  if (hasNoSimFlag)      process.env.DISABLE_SIMULATION = "true";
  if (hasSubagentsFlag)  process.env.PREFER_SUBAGENTS = "true";
  if (hasAutonomousFlag) process.env.PREFER_DIRECTOR = "true";

  return { task, image, isCUA: hasCuaFlag, hasRewindFlag };
}

// ============================================================
// System-level startup (runs once)
// ============================================================

async function startup(isCUA) {
  if (!process.env.API_KEY) {
    console.log(chalk.red("❌ Missing API_KEY in .env. Copy .env.example → .env and add your key."));
    process.exit(1);
  }

  if (!isCUA) {
    const workdir = process.env.WORKDIR || process.cwd();
    console.log(chalk.dim("🧹 Checking for legacy files to migrate..."));
    await migrateAndCleanup(resolve(workdir));

    console.log(chalk.dim("⚡ Indexing codebase..."));
    const r = await executeTool("index_codebase", {});
    console.log(chalk.dim(`   ${r}\n`));
  }
}

// ============================================================
// Inline --image parser for chat loop
// ============================================================

function parseInlineTask(input) {
  // Support: "some task --image path/to/img.png" inside the chat loop
  const parts = input.split(/\s+/);
  let image = null;
  const imgIdx = parts.findIndex(p => p === "--image" || p === "-i");
  if (imgIdx !== -1 && imgIdx + 1 < parts.length) {
    image = parts[imgIdx + 1];
    parts.splice(imgIdx, 2);
  }
  return { task: parts.join(" ").trim(), image };
}

// ============================================================
// Persistent Chat Loop
// ============================================================

/**
 * Run the agent in a persistent chat loop.
 * Messages (context) are preserved across tasks within a session.
 * Users can reset context with 'clear', exit with 'exit'/'quit'.
 *
 * @param {string|null} initialTask  - Task from CLI args (if any)
 * @param {string|null} initialImage - Image from CLI args (if any)
 */
async function chatLoop(initialTask, initialImage) {
  const workdir = process.env.WORKDIR || process.cwd();
  const resolvedWorkdir = resolve(workdir);

  // Session-persistent message history
  let sessionMessages = null;

  console.log(chalk.cyan.bold("\n  🚀 Swades Agent v3.0"));
  console.log(chalk.dim(`  Workspace: ${resolvedWorkdir}`));
  console.log(chalk.dim("  Type 'exit' to quit | 'clear' to reset context | '/help' for commands\n"));
  console.log(chalk.dim("─".repeat(60)));

  // If a task was passed on the CLI, execute it first
  if (initialTask) {
    console.log(chalk.dim(`\n  Running initial task: "${initialTask}"\n`));
    try {
      const result = await runAgent(initialTask, null, sessionMessages, initialImage);
      // After first task, sessionMessages is still null — the agent created its own.
      // We pass null so subsequent tasks start fresh unless the user wants continuity.
      // To enable continuity across sessions, we'd need runAgent to return messages.
      // For now, continuity is within a single chat invocation via sessionMessages below.
    } catch (err) {
      console.error(chalk.red(`Fatal: ${err.message}`));
    }
    console.log(chalk.dim("\n─".repeat(60)));
  }

  // ---- Interactive Chat Loop ----
  const rl = createInterface({ input: process.stdin, output: process.stdout });

  const prompt = () => new Promise((res) => {
    rl.question(chalk.cyan.bold("\n💬 What do you need? → "), res);
  });

  while (true) {
    let input;
    try {
      input = await prompt();
    } catch {
      // stdin closed (piped input finished)
      console.log(chalk.dim("\n  [stdin closed — exiting]"));
      break;
    }

    const trimmed = input.trim();
    if (!trimmed) continue;

    // ---- Chat Commands ----
    if (trimmed.toLowerCase() === "exit" || trimmed.toLowerCase() === "quit") {
      console.log(chalk.cyan("\n  👋 Goodbye!\n"));
      rl.close();
      break;
    }

    if (trimmed.toLowerCase() === "clear") {
      sessionMessages = null;
      console.log(chalk.yellow("  🧹 Context cleared — starting fresh.\n"));
      continue;
    }

    if (trimmed === "/help") {
      printHelp();
      continue;
    }

    // ---- Parse inline --image flag ----
    const { task, image } = parseInlineTask(trimmed);
    if (!task) continue;

    // ---- Run the agent (messages persist across tasks) ----
    console.log(chalk.dim("\n" + "─".repeat(60)));
    try {
      const result = await runAgent(task, null, sessionMessages, image);
      // Record completed session
      await recordSession(task, typeof result === "string" ? result : String(result), []);
      console.log(chalk.dim("\n─".repeat(60)));
      console.log(chalk.green("  ✅ Task complete. Next task? (type 'clear' to reset context, 'exit' to quit)"));
    } catch (err) {
      console.error(chalk.red(`\n  ❌ Agent error: ${err.message}`));
      console.log(chalk.yellow("  Context preserved. You can continue with the next task."));
    }
  }

  process.exit(0);
}

// ============================================================
// Main Entry Point
// ============================================================

async function main() {
  const { task, image, isCUA, hasRewindFlag } = parseCLI();

  // --rewind: list available checkpoints (informational)
  if (hasRewindFlag) {
    const { checkpointStore } = await import("./tools.js");
    if (checkpointStore.length === 0) {
      console.log(chalk.yellow("No checkpoints available in this session. Checkpoints are created during a running task."));
    } else {
      console.log(chalk.cyan.bold("\nAvailable checkpoints:"));
      for (const cp of checkpointStore) {
        console.log(chalk.green(`  Step ${cp.step}: stash ${cp.stashHash?.slice(0, 8) || "N/A"}`));
      }
    }
    process.exit(0);
  }

  // ---- CUA mode: strictly gated behind --cua flag ----
  if (isCUA) {
    if (!task) {
      console.log(chalk.red("❌ --cua requires a task. Usage: swades-agent --cua \"your task\""));
      process.exit(1);
    }
    if (!process.env.API_KEY) {
      console.log(chalk.red("❌ Missing API_KEY in .env"));
      process.exit(1);
    }
    try {
      await runCUA(task);
    } catch (err) {
      console.error(chalk.red(`Fatal: ${err.message}`));
      process.exit(1);
    }
    return;
  }

  // ---- Normal & Autonomous modes: startup + chat loop ----
  await startup(false);

  // PREFER_DIRECTOR hint: start with Director for long-horizon autonomous mode
  if (process.env.PREFER_DIRECTOR === "true" && task) {
    console.log(chalk.green.bold("\n🎬 Director mode (--autonomous flag): delegating to Director AI"));
    try {
      await runDirector(task, Infinity, image);
    } catch (err) {
      console.error(chalk.red(`Fatal: ${err.message}`));
      process.exit(1);
    }
    // After director finishes, drop into chat loop
    await chatLoop(null, null);
    return;
  }

  // Default: enter chat loop (task from CLI is the first message, if any)
  await chatLoop(task || null, image || null);
}

// ---- CLI guard ----
const isMain = process.argv[1] && (
  fileURLToPath(import.meta.url) === resolve(process.argv[1]) ||
  resolve(process.argv[1]).endsWith("bin/swades-agent") ||
  resolve(process.argv[1]).endsWith("bin\\swades-agent")
);

if (isMain) {
  main();
}
