// ============================================================
// director.js — Director AI loop orchestrator (24/7 Autonomy)
// ============================================================

import chalk from "chalk";
import { resolve } from "node:path";
import { runAgent, prepareImageUrl } from "./agent.js";
import { callLLM } from "./llm.js";
import { SYSTEM_PROMPT } from "./prompts.js";
import { getMemoryContext } from "./memory.js";

const DIRECTOR_SYSTEM_PROMPT = `You are the Director AI supervising a software engineering agent.
Your sole job is to act on behalf of the user. You will review the ongoing conversation history and decide what the agent should do next to achieve the user's global goal.

RULES:
1. If the user's global goal is completely and successfully achieved, respond with "STATUS: COMPLETE" followed by a short summary of the accomplished work.
2. If the goal is not yet fully achieved, write a direct, highly specific prompt on behalf of the user directing the agent what to implement, fix, or verify next.
3. Keep your prompt focused and aligned with the user's global goal.
4. Output ONLY the next prompt or "STATUS: COMPLETE". Do not include conversational filler.`;

/**
 * Run the Director AI loop for autonomous 24/7 multi-step execution.
 * The Director AI acts as a virtual user, prompting the agent iteratively
 * within the same continuous conversation history.
 *
 * @param {string} globalGoal - The overall high-level goal
 * @param {number} maxCycles - Safety cap on Director loops
 * @returns {string} - Final completion status
 */
export async function runDirector(globalGoal, maxCycles = Infinity, image = null) {
  console.log(chalk.green.bold("\n🎬 Director AI Activated (24/7 Autonomous Mode)"));
  console.log(chalk.dim(`   Global Goal: "${globalGoal}"`));
  console.log(chalk.dim(`   Max cycles: ${maxCycles === Infinity ? "∞" : maxCycles}\n`));
  console.log(chalk.dim("═".repeat(60)) + "\n");

  // Resolve active workspace directory and load memory
  const workdir = process.env.WORKDIR || process.cwd();
  const resolvedWorkdir = resolve(workdir);
  const memoryContext = await getMemoryContext();

  const workspaceContext = `\n\n## ACTIVE WORKSPACE
Your active workspace directory is: ${resolvedWorkdir}
All tool operations (reading, writing, patching, grep, shell commands) are automatically executed relative to this folder.
Note: The agent's own code folder is completely hidden from your toolbox. You are operating strictly on the user's project codebase.`;

  const systemPrompt = SYSTEM_PROMPT + workspaceContext + memoryContext;

  let userContent = globalGoal;
  if (image) {
    try {
      const imageUrl = await prepareImageUrl(image);
      userContent = [
        { type: "text", text: globalGoal },
        { type: "image_url", image_url: { url: imageUrl } }
      ];
    } catch (err) {
      console.log(chalk.red(`❌ Image prepare failed: ${err.message}`));
      throw err;
    }
  }

  // Initialize the continuous conversation history for the Worker Agent
  const messages = [
    { role: "system", content: systemPrompt },
    { role: "user", content: userContent },
  ];

  for (let cycle = 1; cycle <= maxCycles; cycle++) {
    console.log(chalk.green.bold(`\n🎬 [Director Cycle ${cycle}${maxCycles === Infinity ? "" : `/${maxCycles}`}]`));

    // 1. Run the Worker Agent using the continuous conversation history
    console.log(chalk.cyan(`👷 Worker Agent starting...`));
    await runAgent(null, null, messages);

    // 2. Call the Director AI to review history and prompt on behalf of the user
    console.log(chalk.green(`\n🎬 Director AI reviewing progress...`));
    
    const directorMessages = [
      { role: "system", content: DIRECTOR_SYSTEM_PROMPT },
      ...messages.filter(m => m.role !== "system"), // pass dialogue history for review
      {
        role: "user",
        content: `Review the progress made toward the global goal: "${globalGoal}". 
If the goal is fully achieved, output "STATUS: COMPLETE". 
Otherwise, write the next prompt to send to the agent on behalf of the user.`,
      }
    ];

    const directorResponse = await callLLM(directorMessages);
    const nextPrompt = directorResponse.content.trim();

    if (nextPrompt.includes("STATUS: COMPLETE")) {
      console.log(chalk.green.bold("\n🎉 Director AI declares the global goal FULLY COMPLETE!"));
      console.log(chalk.green(nextPrompt));
      console.log(chalk.dim("\n" + "═".repeat(60) + "\n"));
      return nextPrompt;
    }

    console.log(chalk.green(`\n🎬 Director AI prompt (on behalf of User): `) + chalk.white(nextPrompt));
    console.log(chalk.dim("\n" + "─".repeat(60)));

    // 3. Append the Director's prompt to the continuous history as a user message
    messages.push({ role: "user", content: nextPrompt });
  }

  const msg = `⚠️ Director AI hit the safety cycle limit (${maxCycles}). Stopping.`;
  console.log(chalk.red.bold(`\n${msg}\n`));
  return msg;
}
