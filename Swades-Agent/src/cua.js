// cua.js — Computer Use Agent (CUA) — Lean orchestrator

import chalk from "chalk";
import { execSync } from "node:child_process";
import { resolve } from "node:path";
import { callLLM, MODEL } from "./llm.js";

const CUA_MODEL = process.env.CUA_MODEL || MODEL;

function parseTextToolCall(content) {
  if (!content || typeof content !== "string") return null;

  // 1. Try to find JSON block
  const jsonRegex = /\{[\s\S]*?\}/g;
  let match;
  while ((match = jsonRegex.exec(content)) !== null) {
    try {
      const obj = JSON.parse(match[0]);
      if (obj && typeof obj === "object") {
        const name = obj.name || obj.action || obj.tool || "";
        const nameClean = String(name).toLowerCase();
        
        let toolName = "";
        let args = {};

        if (nameClean.includes("click")) {
          toolName = "cua_click";
          args = { x: obj.x, y: obj.y, button: obj.button, clicks: obj.clicks };
        } else if (nameClean.includes("type")) {
          toolName = "cua_type";
          args = { text: obj.text };
        } else if (nameClean.includes("press")) {
          toolName = "cua_press";
          args = { key: obj.key };
        } else if (nameClean.includes("hotkey")) {
          toolName = "cua_hotkey";
          args = { keys: obj.keys };
        } else if (nameClean.includes("scroll")) {
          toolName = "cua_scroll";
          args = { clicks: obj.clicks };
        } else if (nameClean.includes("move")) {
          toolName = "cua_move";
          args = { x: obj.x, y: obj.y };
        } else if (nameClean.includes("drag")) {
          toolName = "cua_drag";
          args = { x1: obj.x1, y1: obj.y1, x2: obj.x2, y2: obj.y2 };
        } else if (nameClean.includes("zoom")) {
          toolName = "cua_zoom";
          args = { x1: obj.x1, y1: obj.y1, x2: obj.x2, y2: obj.y2 };
        } else if (nameClean.includes("reset")) {
          toolName = "cua_reset_zoom";
          args = {};
        } else if (nameClean.includes("done")) {
          toolName = "cua_done";
          args = { summary: obj.summary };
        } else {
          // Guess from parameter keys if name/action is omitted
          if (obj.keys !== undefined) {
            toolName = "cua_hotkey";
            args = { keys: obj.keys };
          } else if (obj.key !== undefined) {
            toolName = "cua_press";
            args = { key: obj.key };
          } else if (obj.text !== undefined) {
            toolName = "cua_type";
            args = { text: obj.text };
          } else if (obj.x !== undefined && obj.y !== undefined) {
            toolName = "cua_click";
            args = { x: obj.x, y: obj.y, button: obj.button, clicks: obj.clicks };
          } else if (obj.clicks !== undefined) {
            toolName = "cua_scroll";
            args = { clicks: obj.clicks };
          } else if (obj.summary !== undefined) {
            toolName = "cua_done";
            args = { summary: obj.summary };
          }
        }

        if (toolName) {
          Object.keys(args).forEach(key => args[key] === undefined && delete args[key]);
          return {
            id: `call_parsed_${Math.random().toString(36).substr(2, 9)}`,
            type: "function",
            function: {
              name: toolName,
              arguments: JSON.stringify(args)
            }
          };
        }
      }
    } catch (e) {
      // Ignore and keep searching
    }
  }

  // 2. Fallback to regex matches for function-like calls
  const clickMatch = /cua_click\(\s*(\d+)\s*,\s*(\d+)\s*\)/i.exec(content);
  if (clickMatch) {
    return {
      id: `call_parsed_${Math.random().toString(36).substr(2, 9)}`,
      type: "function",
      function: {
        name: "cua_click",
        arguments: JSON.stringify({ x: parseInt(clickMatch[1]), y: parseInt(clickMatch[2]) })
      }
    };
  }

  const typeMatch = /cua_type\(\s*["']([\s\S]*?)["']\s*\)/i.exec(content);
  if (typeMatch) {
    return {
      id: `call_parsed_${Math.random().toString(36).substr(2, 9)}`,
      type: "function",
      function: {
        name: "cua_type",
        arguments: JSON.stringify({ text: typeMatch[1] })
      }
    };
  }

  const pressMatch = /cua_press\(\s*["'](.*?)["']\s*\)/i.exec(content);
  if (pressMatch) {
    return {
      id: `call_parsed_${Math.random().toString(36).substr(2, 9)}`,
      type: "function",
      function: {
        name: "cua_press",
        arguments: JSON.stringify({ key: pressMatch[1] })
      }
    };
  }

  return null;
}

const CUA_SYSTEM = JSON.stringify({
  "role": "Computer Use Agent",
  "task": "Control a Linux desktop using mouse and keyboard actions based on screenshots.",
  "workflow": {
    "step_1_observe": "Output 1-2 lines describing the screen and confirming the cursor's current location (red crosshair) and where it needs to go next.",
    "step_2_act": "Invoke exactly one tool call to perform the next action."
  },
  "rules": [
    "You MUST start every response by stating exactly what you see and confirming the cursor position: 'I see [description]. The cursor is at (X, Y) and I need to get to (X2, Y2) to [action].'",
    "Execute exactly ONE action per step.",
    "Do not guess or hallucinate. Rely strictly on the visual information in the screenshot.",
    "Use absolute pixel coordinates.",
    "When zoomed, coordinates are relative to the crop window (0,0 is the top-left of the crop).",
    "To open an application, press 'super', type its name, and press 'enter'."
  ],
  "tools": {
    "cua_click": "Click at coordinates (x, y). Enum buttons: ['left', 'right', 'middle'].",
    "cua_type": "Type the specified text string.",
    "cua_press": "Press a key: 'enter', 'tab', 'escape', 'backspace', 'space', 'super', 'up', 'down', 'left', 'right'.",
    "cua_hotkey": "Press key combination, e.g. ['ctrl', 'c'].",
    "cua_scroll": "Scroll mouse wheel. Positive value scrolls up, negative scrolls down.",
    "cua_move": "Move cursor to (x, y) without clicking.",
    "cua_drag": "Drag from (x1, y1) to (x2, y2).",
    "cua_zoom": "Crop/zoom into region (x1, y1, x2, y2).",
    "cua_reset_zoom": "Reset zoom back to full screen.",
    "cua_done": "Declare the task complete with a final summary."
  }
}, null, 2);

const TOOLS = [
  {
    type: "function",
    function: {
      name: "cua_click",
      description: "Click at (x, y). In zoom mode, coordinates are relative to the crop window.",
      parameters: {
        type: "object",
        properties: {
          x: { type: "number" },
          y: { type: "number" },
          button: { type: "string", enum: ["left", "right", "middle"] },
          clicks: { type: "integer" }
        },
        required: ["x", "y"]
      }
    }
  },
  {
    type: "function",
    function: {
      name: "cua_type",
      description: "Type text.",
      parameters: {
        type: "object",
        properties: { text: { type: "string" } },
        required: ["text"]
      }
    }
  },
  {
    type: "function",
    function: {
      name: "cua_press",
      description: "Press a key.",
      parameters: {
        type: "object",
        properties: { key: { type: "string" } },
        required: ["key"]
      }
    }
  },
  {
    type: "function",
    function: {
      name: "cua_hotkey",
      description: "Press a combination of keys (e.g. ['ctrl', 'c']).",
      parameters: {
        type: "object",
        properties: { keys: { type: "array", items: { type: "string" } } },
        required: ["keys"]
      }
    }
  },
  {
    type: "function",
    function: {
      name: "cua_scroll",
      description: "Scroll mouse wheel. Positive = up, negative = down.",
      parameters: {
        type: "object",
        properties: { clicks: { type: "integer" } },
        required: ["clicks"]
      }
    }
  },
  {
    type: "function",
    function: {
      name: "cua_move",
      description: "Move mouse to (x, y).",
      parameters: {
        type: "object",
        properties: { x: { type: "number" }, y: { type: "number" } },
        required: ["x", "y"]
      }
    }
  },
  {
    type: "function",
    function: {
      name: "cua_drag",
      description: "Drag mouse from (x1, y1) to (x2, y2).",
      parameters: {
        type: "object",
        properties: { x1: { type: "number" }, y1: { type: "number" }, x2: { type: "number" }, y2: { type: "number" } },
        required: ["x1", "y1", "x2", "y2"]
      }
    }
  },
  {
    type: "function",
    function: {
      name: "cua_zoom",
      description: "Zoom into a region (x1, y1, x2, y2).",
      parameters: {
        type: "object",
        properties: { x1: { type: "number" }, y1: { type: "number" }, x2: { type: "number" }, y2: { type: "number" } },
        required: ["x1", "y1", "x2", "y2"]
      }
    }
  },
  {
    type: "function",
    function: {
      name: "cua_reset_zoom",
      description: "Reset zoom to full screen.",
      parameters: { type: "object", properties: {} }
    }
  },
  {
    type: "function",
    function: {
      name: "cua_done",
      description: "Declare the task complete.",
      parameters: {
        type: "object",
        properties: { summary: { type: "string" } },
        required: ["summary"]
      }
    }
  }
];

function runHelper(args) {
  const helperPath = resolve(process.cwd(), "src/cua_helper.py");
  const argStr = args.map(a => `"${String(a).replace(/"/g, '\\"')}"`).join(" ");
  const output = execSync(`/usr/bin/python3 "${helperPath}" ${argStr}`, {
    encoding: "utf-8",
    timeout: 15000
  });
  return JSON.parse(output.trim());
}

function takeScreenshot(zoom) {
  const args = ["screenshot"];
  if (zoom.active) {
    args.push(zoom.x1, zoom.y1, zoom.x2, zoom.y2);
  }
  return runHelper(args);
}

function makeObservation(actionResult, screenshot) {
  const text = typeof actionResult === "string" ? actionResult : JSON.stringify(actionResult);
  if (!screenshot || screenshot.error) {
    return text + (screenshot?.error ? ` | Screenshot error: ${screenshot.error}` : "");
  }
  const scaleText = screenshot.scale && screenshot.scale !== 1 ? ` | Zoom Scale: ${screenshot.scale}x` : "";
  return {
    text: `Action result: ${text}\nHere is the updated screenshot after your action.\nScreen Resolution: ${screenshot.width}x${screenshot.height}\nMouse cursor (red crosshair): at pixel (${screenshot.mouse.x}, ${screenshot.mouse.y})${scaleText}\n\nYou MUST start your response with exactly 1-2 lines describing what you see and confirming the cursor position: "I see [what is on screen]. The cursor is at (${screenshot.mouse.x}, ${screenshot.mouse.y}) and I need to get to (X2, Y2) to..."`,
    base64: screenshot.base64
  };
}

function sanitizeMessagesTextOnly(messages) {
  for (const msg of messages) {
    if (Array.isArray(msg.content)) {
      const textParts = msg.content
        .filter(item => item.type === "text")
        .map(item => item.text);
      msg.content = textParts.join("\n");
    }
  }
}

function keepOnlyLatestImage(messages) {
  let lastImageMsgIndex = -1;
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === "user" && Array.isArray(messages[i].content)) {
      if (messages[i].content.some(item => item.type === "image_url")) {
        lastImageMsgIndex = i;
        break;
      }
    }
  }

  if (lastImageMsgIndex !== -1) {
    for (let i = 0; i < messages.length; i++) {
      if (i === lastImageMsgIndex) continue;
      const msg = messages[i];
      if (Array.isArray(msg.content)) {
        const textParts = msg.content
          .filter(item => item.type === "text")
          .map(item => item.text);
        msg.content = textParts.join("\n");
      }
    }
  }
}

export async function runCUA(globalGoal, maxSteps = 40) {
  console.log(chalk.magenta.bold("\n🖥️  CUA Mode"));
  console.log(chalk.dim(`   Goal: "${globalGoal}"`));
  console.log(chalk.dim(`   Model: ${CUA_MODEL} | Max steps: ${maxSteps}\n`));

  const zoom = { active: false, x1: 0, y1: 0, x2: 1920, y2: 1080, w: 1920, h: 1080 };

  let screen;
  try {
    screen = takeScreenshot(zoom);
  } catch (e) {
    console.log(chalk.red(`❌ Screenshot failed: ${e.message}`));
    return "CUA aborted: no screenshot.";
  }
  if (screen.error) {
    console.log(chalk.red(`❌ ${screen.error}`));
    return `CUA aborted: ${screen.error}`;
  }

  const messages = [
    { role: "system", content: CUA_SYSTEM },
    {
      role: "user",
      content: [
        { type: "text", text: `Task: ${globalGoal}\n\nHere is a screenshot of the current screen.\nScreen Resolution: ${screen.width}x${screen.height}\nMouse cursor (red crosshair): at pixel (${screen.mouse.x}, ${screen.mouse.y})\n\nYou MUST start your response with exactly 1-2 lines describing what you see and confirming the cursor position: "I see [what is on screen]. The cursor is at (${screen.mouse.x}, ${screen.mouse.y}) and I need to get to (X2, Y2) to..."` },
        { type: "image_url", image_url: { url: `data:image/jpeg;base64,${screen.base64}` } }
      ]
    }
  ];

  let noToolCount = 0;
  const clickHistory = [];

  for (let step = 1; step <= maxSteps; step++) {
    console.log(chalk.yellow(`⚡ Step ${step}/${maxSteps}`));
    keepOnlyLatestImage(messages);

    let response;
    let retries = 2;
    let isTextOnlyFallback = false;
    
    while (retries >= 0) {
      try {
        let header = false;
        response = await callLLM(messages, TOOLS, (chunk) => {
          if (chunk.type === "content") {
            if (!header) { process.stdout.write(chalk.blue("💭 ")); header = true; }
            process.stdout.write(chalk.blue(chunk.text));
          } else if (chunk.type === "tool_name" && chunk.name) {
            process.stdout.write(chalk.magenta(`\n   🔧 ${chunk.name}`));
          } else if (chunk.type === "tool_args" && chunk.args) {
            process.stdout.write(chalk.gray(chunk.args));
          }
        }, CUA_MODEL);
        console.log();
        break;
      } catch (e) {
        console.log(chalk.red(`\n   ❌ ${e.message}`));
        const isImageError = e.message.includes("400") || e.message.toLowerCase().includes("image") || e.message.toLowerCase().includes("vision");
        if (isImageError && !isTextOnlyFallback) {
          console.log(chalk.yellow("   ⚠ Image upload or vision not supported. Sanitizing message history to text-only..."));
          sanitizeMessagesTextOnly(messages);
          isTextOnlyFallback = true;
          retries++;
        }
        retries--;
        if (retries < 0) {
          if (isImageError) {
            console.log(chalk.yellow("   ⚠ Attempting final emergency fallback execution as pure text..."));
            try {
              response = await callLLM(messages, TOOLS, null, CUA_MODEL);
              break;
            } catch (finalErr) {
              return `CUA error: ${finalErr.message}`;
            }
          }
          return `CUA error: ${e.message}`;
        }
        console.log(chalk.dim(`   Retrying (${retries} left)...`));
      }
    }

    messages.push(response);

    if (!response.tool_calls || response.tool_calls.length === 0) {
      const parsedTool = parseTextToolCall(response.content);
      if (parsedTool) {
        response.tool_calls = [parsedTool];
      }
    }

    if (!response.tool_calls || response.tool_calls.length === 0) {
      noToolCount++;
      const nudgeMessage = `You must invoke exactly ONE tool to proceed. Use cua_click, cua_type, etc. or cua_done if finished.`;
      if (noToolCount > 4) {
        console.log(chalk.red("   ❌ Model repeatedly failed to invoke tools. Aborting."));
        return "CUA aborted: no tool calls.";
      }
      console.log(chalk.yellow(`   ⚠ Model did not invoke a tool. Retrying (${4 - noToolCount} attempts left)...`));
      messages.push({ role: "user", content: nudgeMessage });
      continue;
    }
    noToolCount = 0;

    const tc = response.tool_calls[0];
    const name = tc.function.name;
    const args = typeof tc.function.arguments === "string" ? JSON.parse(tc.function.arguments) : tc.function.arguments;

    console.log(chalk.magenta(`   → ${name}(${JSON.stringify(args)})`));

    let result;
    let isDone = false;

    const tx = (val) => zoom.active ? zoom.x1 + Math.round(Number(val)) : Math.round(Number(val));
    const ty = (val) => zoom.active ? zoom.y1 + Math.round(Number(val)) : Math.round(Number(val));

    try {
      switch (name) {
        case "cua_click":
          const currentX = Number(args.x);
          const currentY = Number(args.y);
          
          let isConsecutive = false;
          if (clickHistory.length > 0) {
            const lastClick = clickHistory[clickHistory.length - 1];
            if (Math.abs(lastClick.x - currentX) <= 25 && Math.abs(lastClick.y - currentY) <= 15) {
              isConsecutive = true;
            }
          }

          const occurrences = clickHistory.filter(c => {
            const dx = Math.abs(c.x - currentX);
            const dy = Math.abs(c.y - currentY);
            return dx <= 25 && dy <= 15;
          }).length;

          if (isConsecutive) {
            console.log(chalk.red("   ❌ Declined: Cannot click in the same place consecutively (back-to-back)."));
            result = { error: "Declined: You cannot click the same area consecutively (back-to-back). Please examine the screen, choose a different coordinate, or try a different approach (e.g. typing or moving elsewhere first)." };
          } else if (occurrences >= 2) {
            console.log(chalk.red("   ❌ Declined: Clicked this place more than twice overall."));
            result = { error: "Declined: You have already clicked this same area 2 times during this task. To prevent infinite loops, clicking the same place more than twice is not allowed. Please choose a different coordinate or try a different approach." };
          } else {
            result = runHelper(["click", tx(currentX), ty(currentY), args.button || "left", args.clicks || 1]);
            clickHistory.push({ x: currentX, y: currentY });
          }
          break;
        case "cua_type":
          result = runHelper(["type", args.text]);
          break;
        case "cua_press":
          result = runHelper(["press", args.key]);
          break;
        case "cua_hotkey":
          result = runHelper(["hotkey", ...args.keys]);
          break;
        case "cua_scroll":
          result = runHelper(["scroll", args.clicks]);
          break;
        case "cua_move":
          result = runHelper(["move", tx(args.x), ty(args.y)]);
          break;
        case "cua_drag":
          result = runHelper(["drag", tx(args.x1), ty(args.y1), tx(args.x2), ty(args.y2)]);
          break;
        case "cua_zoom":
          zoom.active = true;
          zoom.x1 = tx(args.x1);
          zoom.y1 = ty(args.y1);
          zoom.x2 = tx(args.x2);
          zoom.y2 = ty(args.y2);
          zoom.w = zoom.x2 - zoom.x1;
          zoom.h = zoom.y2 - zoom.y1;
          result = { status: "ok", action: "zoom" };
          break;
        case "cua_reset_zoom":
          zoom.active = false;
          zoom.x1 = 0;
          zoom.y1 = 0;
          zoom.x2 = screen.width || 1920;
          zoom.y2 = screen.height || 1080;
          zoom.w = zoom.x2;
          zoom.h = zoom.y2;
          result = { status: "ok", action: "reset_zoom" };
          break;
        case "cua_done":
          isDone = true;
          result = { status: "complete", summary: args.summary || "Done" };
          break;
        default:
          result = { error: `Unknown tool: ${name}` };
      }
    } catch (e) {
      result = { error: e.message };
    }

    if (isDone) {
      const summary = args.summary || "Done";
      messages.push({ role: "tool", tool_call_id: tc.id, content: `Task complete: ${summary}` });
      console.log(chalk.green.bold(`\n✅ CUA complete: ${summary}\n`));
      return summary;
    }

    let obs;
    try {
      const newScreen = takeScreenshot(zoom);
      const hint = result?._hint ? ` | HINT: ${result._hint}` : "";
      obs = makeObservation(result, newScreen);
      if (typeof obs === "object") obs.text += hint;
      else obs += hint;
    } catch (e) {
      obs = makeObservation(result, null);
    }

    const toolResultText = typeof result === "string" ? result : JSON.stringify(result);
    messages.push({
      role: "tool",
      tool_call_id: tc.id,
      content: toolResultText
    });

    if (typeof obs === "object" && obs.base64) {
      messages.push({
        role: "user",
        content: [
          { type: "text", text: obs.text },
          { type: "image_url", image_url: { url: `data:image/jpeg;base64,${obs.base64}` } }
        ]
      });
    } else {
      messages.push({
        role: "user",
        content: typeof obs === "string" ? obs : JSON.stringify(obs)
      });
    }

    console.log(chalk.dim("─".repeat(50)));
  }

  console.log(chalk.red.bold(`\n⚠ Hit ${maxSteps}-step limit.\n`));
  return `CUA stopped: ${maxSteps}-step limit.`;
}
