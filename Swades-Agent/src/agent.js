// agent.js — ReAct loop orchestrator (THINK → ACT → OBSERVE)
// Now with: Loop Detection, Stack Detection, Cache-Isolated Index

import chalk from "chalk";
import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { resolve, extname } from "node:path";
import { exec } from "node:child_process";
import { callLLM, MODEL } from "./llm.js";
import { executeTool, activeDeadline, detectProjectStack, checkpointStore } from "./tools.js";
import { SYSTEM_PROMPT, TOOL_SCHEMAS } from "./prompts.js";
import { getMemoryContext, recordSession } from "./memory.js";
import { getSwadesCacheDir } from "./cleanup.js";

// Shell helper for git stash snapshots
function shell(cmd, cwd) {
  return new Promise((resolve, reject) => {
    exec(cmd, { cwd, maxBuffer: 1024 * 1024, timeout: 10000 }, (err, stdout, stderr) => {
      if (err) return reject(new Error(stderr || err.message));
      resolve((stdout || "").trim());
    });
  });
}

// ============================================================
// LoopDetector — Prevents infinite loops and repetitive behavior
// ============================================================

class LoopDetector {
  constructor() {
    this.history = [];          // [{name, argsHash, step}]
    this.stagnantSteps = 0;     // consecutive steps without file changes
    this.indexReads = 0;        // times .agent_index.json was read
    this.MAX_REPEAT = 3;        // max identical consecutive calls
    this.MAX_STAGNANT = 4;      // max steps without progress
    this.MAX_INDEX_READS = 1;   // max times to re-read the index file
  }

  /**
   * Hash tool call arguments for comparison.
   */
  _hashArgs(args) {
    const str = typeof args === "string" ? args : JSON.stringify(args || {});
    return createHash("md5").update(str).digest("hex").slice(0, 12);
  }

  /**
   * Record a tool call and check for loops.
   * @returns {string|null} - Warning message if loop detected, null otherwise
   */
  recordCall(name, args, step) {
    const argsHash = this._hashArgs(args);
    this.history.push({ name, argsHash, step });

    // ---- Check 1: Block repeated reads of .agent_index.json ----
    const parsedArgs = typeof args === "string" ? (() => { try { return JSON.parse(args); } catch { return {}; } })() : (args || {});
    if (name === "read_file" && parsedArgs.path && parsedArgs.path.includes("agent_index.json")) {
      this.indexReads++;
      if (this.indexReads > this.MAX_INDEX_READS) {
        return `⚠️ [LOOP BLOCKED] You already have the codebase index in your system prompt. Do NOT re-read .agent_index.json. Focus on the actual task files instead.`;
      }
    }

    // ---- Check 2: Detect identical consecutive calls ----
    if (this.history.length >= this.MAX_REPEAT) {
      const recent = this.history.slice(-this.MAX_REPEAT);
      const allSame = recent.every(
        (call) => call.name === recent[0].name && call.argsHash === recent[0].argsHash
      );
      if (allSame) {
        return `⚠️ [LOOP DETECTED] You have called '${name}' with identical arguments ${this.MAX_REPEAT} times in a row. This is unproductive. Change your strategy: try a different file, tool, or approach. If you're stuck, explain what's blocking you and call a different tool.`;
      }
    }

    return null;
  }

  /**
   * Track whether a step made progress (file modification).
   * @param {string[]} toolNames - Tool names called in this step
   * @returns {string|null} - Warning if stagnant, null otherwise
   */
  recordProgress(toolNames) {
    const progressTools = ["write_file", "patch_file", "run_command"];
    const madeProgress = toolNames.some((t) => progressTools.includes(t));

    if (madeProgress) {
      this.stagnantSteps = 0;
      return null;
    }

    this.stagnantSteps++;
    if (this.stagnantSteps >= this.MAX_STAGNANT) {
      return `⚠️ [STAGNATION WARNING] You have gone ${this.stagnantSteps} consecutive steps without modifying any files or running commands. You appear to be stuck in a read-only loop. Take action: write code, patch a file, or run a command. If you cannot proceed, explain the blocker.`;
    }

    return null;
  }
}

/**
 * Prepare an image URL for OpenAI multimodal schema.
 * Supports web URLs and local file paths (converting local files to base64 data URIs).
 *
 * @param {string} imagePathOrUrl
 * @returns {Promise<string>}
 */
export async function prepareImageUrl(imagePathOrUrl) {
  if (!imagePathOrUrl) return null;

  if (imagePathOrUrl.startsWith("http://") || imagePathOrUrl.startsWith("https://") || imagePathOrUrl.startsWith("data:")) {
    return imagePathOrUrl;
  }

  const workdir = process.env.WORKDIR || process.cwd();
  let filePath = resolve(imagePathOrUrl);
  if (!existsSync(filePath)) {
    filePath = resolve(workdir, imagePathOrUrl);
  }

  if (!existsSync(filePath)) {
    throw new Error(`Image file not found: ${imagePathOrUrl}`);
  }

  const buffer = await readFile(filePath);
  const base64Data = buffer.toString("base64");

  const ext = extname(filePath).toLowerCase();
  let mimeType = "image/png";
  if (ext === ".jpg" || ext === ".jpeg") {
    mimeType = "image/jpeg";
  } else if (ext === ".gif") {
    mimeType = "image/gif";
  } else if (ext === ".webp") {
    mimeType = "image/webp";
  }

  return `data:${mimeType};base64,${base64Data}`;
}

/**
 * Run the ReAct agentic loop.
 * @param {string} task - User's task
 * @param {number} maxSteps - Safety cap (default Infinity)
 * @param {Array} existingMessages - Continue from existing conversation
 * @param {string} image - Optional image path or URL
 * @returns {string} - Final answer
 */
export async function runAgent(task, maxSteps, existingMessages, image, onEvent = null) {
  const max = maxSteps || parseInt(process.env.MAX_STEPS) || Infinity;
  let messages = existingMessages;

  // NOTE: The old orchestrator gate was here (auto-routing to runOrchestrated).
  // It has been removed. The agent now starts directly in the ReAct loop
  // and uses run_simulation / spawn_subagents / delegate_to_director tools
  // mid-flight whenever the task complexity demands it.

  if (!messages) {
    const workdir = process.env.WORKDIR || process.cwd();
    const resolvedWorkdir = resolve(workdir);

    // Load codebase index from cache directory (not project root)
    let indexContext = "";
    const cacheDir = getSwadesCacheDir(resolvedWorkdir);
    const indexFile = resolve(cacheDir, "agent_index.json");
    if (existsSync(indexFile)) {
      try {
        const index = JSON.parse(await readFile(indexFile, "utf-8"));
        const files = Object.keys(index.files);
        if (files.length > 0) {
          indexContext = `\n\n## CODEBASE STRUCTURE\n${files.map(f => {
            const s = index.files[f].structure || { functions: [], classes: [] };
            const d = [];
            if (s.classes?.length) d.push(`classes: [${s.classes.join(", ")}]`);
            if (s.functions?.length) d.push(`funcs: [${s.functions.join(", ")}]`);
            return `- ${f} (${d.join("; ") || "file"})`;
          }).join("\n")}`;
        }
      } catch (e) {
        console.log(chalk.dim(`⚠ Index load failed: ${e.message}`));
      }
    }

    // Detect project stack for context-aware behavior
    let stackContext = "";
    try {
      const stack = await detectProjectStack(resolvedWorkdir);
      if (stack.language !== "unknown") {
        stackContext = `\n\n## DETECTED PROJECT STACK
- Language: ${stack.language}
- Runtime: ${stack.runtime}
- Framework: ${stack.framework}
- Package Manager: ${stack.packageManager}
- Details: ${stack.details.join(", ")}

STACK RULES:
- Generate code compatible with the detected language and runtime.
- Do NOT spawn Python subprocesses in a JavaScript/TypeScript project unless explicitly asked.
- Do NOT generate JavaScript code for a Python project unless explicitly asked.
- Match the project's existing coding patterns and conventions.`;
      }
    } catch (stackErr) {
      console.log(chalk.dim(`⚠ Stack detection failed: ${stackErr.message}`));
    }

    const memoryContext = await getMemoryContext();

    const workspaceContext = `\n\n## WORKSPACE\nActive directory: ${resolvedWorkdir}\nAll tool operations run relative to this folder.`;

    let userContent = task;
    if (image) {
      try {
        const imageUrl = await prepareImageUrl(image);
        userContent = [
          { type: "text", text: task },
          { type: "image_url", image_url: { url: imageUrl } }
        ];
      } catch (err) {
        console.log(chalk.red(`❌ Image prepare failed: ${err.message}`));
        throw err;
      }
    }

    messages = [
      { role: "system", content: SYSTEM_PROMPT + workspaceContext + indexContext + stackContext + memoryContext },
      { role: "user", content: userContent },
    ];
  }

  const toolsUsed = new Set();
  const loopDetector = new LoopDetector();
  // Track mutating steps for checkpoint deduplication
  let lastCheckpointStep = -1;
  const workdir = process.env.WORKDIR || process.cwd();
  const resolvedWorkdir = resolve(workdir);

  // ---- Context Window Pruner ----
  function pruneContext(msgs) {
    if (msgs.length <= 40) return msgs;
    const systemMsgs = msgs.filter(m => m.role === "system");
    const recent = msgs.slice(-15);
    const middle = msgs.slice(systemMsgs.length, msgs.length - 15);
    const summary = `[CONTEXT PRUNED: ${middle.length} older messages compressed to save context. Those steps covered file reads, patches, and verifications. Current workspace state reflects all those changes.]`;
    return [...systemMsgs, { role: "user", content: summary }, ...recent];
  }

  let estimatedDurationSeconds = 180;
  if (!existingMessages && task) {
    console.log(chalk.dim("⏰ AI is estimating the optimal task deadline..."));
    try {
      const estimationPrompt = [
        {
          role: "system",
          content: "You are the time estimator for Swades Agent. Estimate how many seconds this task should take to execute under ordinary circumstances. Be realistic and consider code writing, file searches, testing, and debugging. Respond with ONLY a single integer representing seconds (e.g. 120). Minimum: 30 seconds, Maximum: 600 seconds. Do not write any other text."
        },
        {
          role: "user",
          content: `Task: ${task}`
        }
      ];
      const res = await callLLM(estimationPrompt);
      const seconds = parseInt(res.content?.trim());
      if (!isNaN(seconds) && seconds >= 30 && seconds <= 600) {
        estimatedDurationSeconds = seconds;
      }
    } catch (err) {
      console.log(chalk.dim(`   (AI time estimation failed: ${err.message}. Defaulting to 180s.)`));
    }
    console.log(chalk.cyan(`   (AI allocated task time: ${estimatedDurationSeconds} seconds)`));
    
    activeDeadline.estimatedSeconds = estimatedDurationSeconds;
    activeDeadline.startTime = Date.now();
  } else {
    activeDeadline.startTime = Date.now();
    activeDeadline.estimatedSeconds = activeDeadline.estimatedSeconds || 180;
  }

  console.log(chalk.cyan.bold("\n🤖 Agent started"));
  console.log(chalk.dim(`   Model: ${MODEL} | Steps: ${max === Infinity ? "∞" : max} | Task: ${task || "continuing"}\n`));

  let graceStepsLeft = 3;

  for (let step = 1; step <= max; step++) {
    console.log(chalk.yellow(`⚡ Step ${step}${max === Infinity ? "" : `/${max}`}`));

    const elapsed = Math.round((Date.now() - activeDeadline.startTime) / 1000);
    const remaining = activeDeadline.estimatedSeconds - elapsed;

    let urgencyLevel = "CALM";
    let pressureGuideline = "Plenty of time left. Focus on clean code, validation, and complete solutions.";
    let timerColor = chalk.green;
    
    const pct = remaining / activeDeadline.estimatedSeconds;
    if (remaining <= 0) {
      urgencyLevel = "OVERTIME";
      pressureGuideline = "🚨 DEADLINE EXPIRED: You are running in OVERTIME! You MUST wrap up immediately. If you need more time to finish cleanly, explain why and call the 'extend_deadline' tool now to prevent forced shutdown.";
      timerColor = chalk.bgRed.white.bold;
    } else if (pct < 0.1) {
      urgencyLevel = "PANIC";
      pressureGuideline = "⚠️ CRITICAL TIME PRESSURE: Time is almost up! Omit extra steps, focus purely on resolving the core task and finishing immediately.";
      timerColor = chalk.red.bold;
    } else if (pct < 0.3) {
      urgencyLevel = "URGENT";
      pressureGuideline = "Time is running low. Avoid round-trips, run tests quickly, and resolve the final steps.";
      timerColor = chalk.red;
    } else if (pct < 0.6) {
      urgencyLevel = "MEDIUM";
      pressureGuideline = "Time is ticking. Work efficiently and avoid repeating commands.";
      timerColor = chalk.yellow;
    }

    if (remaining <= 0) {
      graceStepsLeft--;
      if (graceStepsLeft < 0) {
        const errorMsg = `🚨 [LOOP PREVENTION] Task terminated: Deadline exceeded and grace step limit reached without extension.`;
        console.log(chalk.red.bold(`\n${errorMsg}\n`));
        await recordSession(task, errorMsg, [...toolsUsed]);
        return errorMsg;
      }
    }

    const barWidth = 20;
    const filledWidth = Math.max(0, Math.min(barWidth, Math.round(pct * barWidth)));
    const emptyWidth = barWidth - filledWidth;
    const barStr = "█".repeat(filledWidth) + "░".repeat(emptyWidth);
    
    const remainingText = remaining <= 0 ? `OVERTIME (${Math.abs(remaining)}s overdue)` : `${remaining}s remaining`;
    console.log(timerColor(`⏰ TIMER: ${remainingText} / ${activeDeadline.estimatedSeconds}s [${barStr}] URGENCY: ${urgencyLevel}`));
    if (remaining <= 0) {
      console.log(chalk.red(`   ⚠️ Grace steps left: ${graceStepsLeft + 1} steps`));
    }

    const timePressureContext = `\n\n## URGENT TIMING AND DEADLINE SYSTEM
- Task Start Time: ${new Date(activeDeadline.startTime).toISOString()}
- Current Time: ${new Date().toISOString()}
- Total Allocated Duration: ${activeDeadline.estimatedSeconds}s
- Elapsed Time: ${elapsed}s
- Remaining Time: ${remainingText}
- Urgency Level: ${urgencyLevel}
- Critical Instruction: ${pressureGuideline}
${remaining <= 0 ? `- GRACE WARNING: You will be forcibly terminated in ${graceStepsLeft + 1} steps if you do not complete the task or use 'extend_deadline'.` : ""}`;

    if (!messages[0]._originalContent) {
      messages[0]._originalContent = messages[0].content;
    }
    messages[0].content = messages[0]._originalContent + timePressureContext;

    let response;
    let header = false;
    let fullThought = "";

    try {
      if (onEvent) onEvent('status', `Step ${step}${max === Infinity ? "" : `/${max}`}: Consulting OpenRouter AI models...`);
      response = await callLLM(messages, TOOL_SCHEMAS, (chunk) => {
        if (chunk.type === "content") {
          fullThought += chunk.text || "";
          if (!header) { process.stdout.write(chalk.blue("💭 ")); header = true; }
          process.stdout.write(chalk.blue(chunk.text));
        } else if (chunk.type === "tool_name" && chunk.name) {
          process.stdout.write(chalk.magenta(`\n   🔧 ${chunk.name}`));
        } else if (chunk.type === "tool_args" && chunk.args) {
          process.stdout.write(chalk.gray(chunk.args));
        }
      }, null, onEvent);
      console.log();
      if (onEvent && fullThought) {
        onEvent('thinking', fullThought);
      }
    } catch (err) {
      console.log(chalk.red(`\n   ❌ ${err.message}`));
      if (onEvent) onEvent('status', `Model issue: ${err.message}`);
      if (step < max) { console.log(chalk.yellow("   Retrying...\n")); continue; }
      return `Agent error: ${err.message}`;
    }

    messages.push(response);

    // No tool calls → final answer
    if (!response.tool_calls?.length) {
      const answer = response.content || "(no response)";
      console.log(chalk.green("\n💬 Answer:\n"));
      console.log(answer);
      console.log(chalk.green.bold("\n✅ Done\n"));
      await recordSession(task, answer, [...toolsUsed]);
      if (onEvent) onEvent('thinking', answer);
      return answer;
    }

    // Execute tools with loop detection
    const stepToolNames = [];
    const MUTATING_TOOLS = new Set(["write_file", "patch_file", "run_command"]);

    for (const toolCall of response.tool_calls) {
      const { name, arguments: args } = toolCall.function;
      toolsUsed.add(name);
      stepToolNames.push(name);
      console.log(chalk.magenta(`   → ${name}`));

      // ---- Git State Checkpoint (before any mutating tool) ----
      if (MUTATING_TOOLS.has(name) && lastCheckpointStep !== step) {
        lastCheckpointStep = step;
        try {
          const stashHash = await shell("git stash create", resolvedWorkdir);
          if (stashHash) {
            checkpointStore.push({
              step,
              stashHash,
              messagesSnapshot: JSON.parse(JSON.stringify(messages)),
            });
            // Keep only last 10 checkpoints to cap memory
            if (checkpointStore.length > 10) checkpointStore.shift();
            console.log(chalk.dim(`   💾 Checkpoint saved: step ${step} (stash: ${stashHash.slice(0, 8)})`))
          }
        } catch { /* non-fatal — git may not be initialized in this workspace */ }
      }

      // ---- Loop Detection: check before execution ----
      const loopWarning = loopDetector.recordCall(name, args, step);
      if (loopWarning) {
        console.log(chalk.red.bold(`   ${loopWarning}`));
        if (onEvent) onEvent('status', loopWarning);
        // Return the warning as the tool result instead of executing
        messages.push({ role: "tool", tool_call_id: toolCall.id, content: loopWarning });
        continue;
      }

      if (onEvent) onEvent('tool_start', { tool: name, args });
      const result = await executeTool(name, args);
      const preview = result.length > 200 ? result.slice(0, 200) + chalk.dim(`... (${result.length} chars)`) : result;
      console.log(chalk.gray(`   ${preview.split("\n").join("\n   ")}\n`));
      if (onEvent) {
        onEvent('tool_end', { tool: name, result: result });
        if (MUTATING_TOOLS.has(name)) {
          try {
            const currentDiff = await shell("git diff", resolvedWorkdir);
            if (currentDiff) {
              onEvent('diff_update', { diff: currentDiff });
            }
          } catch(e) {}
        }
      }

      messages.push({ role: "tool", tool_call_id: toolCall.id, content: result });

      // ---- Rewind signal from rewind_to_checkpoint tool ----
      if (name === "rewind_to_checkpoint" && process.env._SWADES_REWIND_STEP) {
        const rewindStep = parseInt(process.env._SWADES_REWIND_STEP);
        delete process.env._SWADES_REWIND_STEP;
        const checkpoint = checkpointStore.find(c => c.step === rewindStep)
          || checkpointStore[checkpointStore.length - 1];
        if (checkpoint?.messagesSnapshot) {
          console.log(chalk.cyan.bold(`   ⏮️  Context rewound to step ${checkpoint.step}`));
          // Restore message history to the checkpoint state, keep the rewind tool result
          const rewindResult = messages[messages.length - 1];
          messages.length = 0;
          messages.push(...checkpoint.messagesSnapshot);
          messages.push(rewindResult);
        }
        break; // Exit tool loop — fresh loop will start from rewound context
      }
    }

    // ---- Stagnation Detection: check after step ----
    const stagnationWarning = loopDetector.recordProgress(stepToolNames);
    if (stagnationWarning) {
      console.log(chalk.red.bold(`   ${stagnationWarning}`));
      // Inject as a system-level nudge
      messages.push({
        role: "user",
        content: stagnationWarning,
      });
    }

    // ---- Context Window Pruning (every step, if messages are large) ----
    if (messages.length > 40) {
      const prunedMessages = pruneContext(messages);
      if (prunedMessages.length < messages.length) {
        console.log(chalk.dim(`   🧹 Context pruned: ${messages.length} → ${prunedMessages.length} messages`));
        messages.length = 0;
        messages.push(...prunedMessages);
      }
    }

    console.log(chalk.dim("─".repeat(50)));
  }

  const msg = `⚠ Hit ${max}-step limit.`;
  console.log(chalk.red.bold(`\n${msg}\n`));
  await recordSession(task, msg, [...toolsUsed]);
  return msg;
}
