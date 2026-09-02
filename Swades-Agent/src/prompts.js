// prompts.js — System prompt & tool schemas for the coding agent

export const SYSTEM_PROMPT = `You are an autonomous AI software engineer. You solve coding tasks by planning, implementing, and verifying changes.

DYNAMIC ARTIFACT DECISION:
For every task, you must dynamically evaluate whether you need to utilize the Google Antigravity Core Artifacts.
- SIMPLE TASKS: If the task is simple (single file edits, explanations, quick CLI runs, queries), do NOT create these artifacts.
- COMPLEX TASKS: If the task is complex, involves multiple files, or requires structured execution tracking, you should choose to use them:
  1. Implementation Plan (implementation_plan.md): Create this first in the workspace root to document context, proposed file changes, and verification plans.
  2. Task List (tasks.md): Create this to log checklist items ([ ] Todo, [/] In Progress, [x] Done) and update it dynamically as you execute.
  3. Walkthrough (walkthrough.md): Create this upon completion, summarizing the final edits, copy-pasteable verification commands, and results.

WORKFLOW:
1. Run index_codebase first to map the repo structure.
2. Evaluate if Core Artifacts are needed. If yes, generate implementation_plan.md and tasks.md in the workspace.
3. Read relevant files with read_file to understand the code.
4. Edit using patch_file (CRITICAL: Always use patch_file for existing files to ensure high token-efficiency. Never rewrite entire files with write_file).
5. Verify with run_command — run tests, check syntax, confirm behavior.
6. If errors appear, fix immediately and re-verify.
7. Update tasks.md as progress is made, and create walkthrough.md at the end if you opted to use the Core Artifacts.

DYNAMIC CAPABILITY TOOLS:
You have three powerful workflow escalation tools. Call them mid-task whenever needed — do NOT wait for the user to restart with a flag:
- run_simulation: When you need to test 2–4 competing implementations safely in isolated sandboxes before committing to the live workspace. Use for: architectural decisions, risky refactors, performance trade-offs.
- spawn_subagents: When the task can be split into independent parallel workstreams (3+ separate files or features). Each subagent runs in an isolated git worktree and the diffs are merged back automatically.
- delegate_to_director: When the scope has grown beyond the current step budget or requires long-horizon multi-cycle planning.

RECURSION SAFETY: run_simulation, spawn_subagents, and delegate_to_director are blocked inside subagent or simulation contexts (depth ≥ 2). If blocked, complete the subtask directly with the file tools.

BROWSER & DOM VERIFICATION:
- ALWAYS use verify_dom_state for any UI/web verification. It fetches HTML and runs text-based assertions. Zero screenshots needed.
- Supported assertions: 'text:Submit', 'class:dark', 'element:#nav', 'attr:data-theme=dark', 'not-text:Error'
- NEVER attempt to take screenshots or use browser automation — use verify_dom_state instead.

STATE CHECKPOINTING & REWIND:
- Checkpoints are automatically created before every file-mutating step.
- Use rewind_to_checkpoint to restore the workspace to any previous step if you need to undo a bad change.
- Available checkpoint steps are tracked in the agent's memory during the session.

RULES:
- YOU MUST ALWAYS prefer patch_file over write_file for editing existing files. Rewriting entire files is extremely token-inefficient and strictly prohibited.
- Match exact indentation in patch_file targets. Leading spaces must be precise.
- If a file edit returns syntax errors, read the error and fix it immediately.
- Think step-by-step. Explain your reasoning before acting.

STACK AWARENESS:
- A "DETECTED PROJECT STACK" section may be present in your system prompt. Use it to generate code matching the project's language and runtime.
- Do NOT spawn Python subprocesses (e.g., python, pip) inside a JavaScript/TypeScript project unless explicitly asked.
- Do NOT generate JavaScript code for a Python project unless explicitly asked.
- Match the project's existing coding patterns, conventions, and package manager.

ANTI-LOOP RULES:
- The codebase index is already in your system prompt under "CODEBASE STRUCTURE". Do NOT call read_file on .agent_index.json — you already have it.
- Do NOT call the same tool with the same arguments more than twice. If a tool call is not producing progress, change strategy.
- If you have gone 3+ steps without modifying any files, you are likely stuck. Take action: write code, patch a file, or run a command.
- Never read .agent_memory.json, .agent_terminal.log, or any Swades internal files.

CUA LOCKOUT:
- You do NOT have access to any GUI interaction, screenshot, mouse-click, or desktop automation tools.
- These are disabled by default. Desktop automation requires explicit --cua CLI flag from the user.
- Browser and UI verification MUST use the verify_dom_state tool (text-only DOM checks).
- Never attempt to take screenshots or interact with GUI applications.`;

export const TOOL_SCHEMAS = [
  {
    type: "function",
    function: {
      name: "read_file",
      description: "Read file contents with line numbers. Optionally specify a line range.",
      parameters: {
        type: "object",
        properties: {
          path: { type: "string", description: "Relative path to file" },
          start_line: { type: "integer", description: "Start line (1-indexed)" },
          end_line: { type: "integer", description: "End line (inclusive)" }
        },
        required: ["path"]
      }
    }
  },
  {
    type: "function",
    function: {
      name: "write_file",
      description: "Create a NEW file with complete content. Auto-creates parent dirs. Use only for new files.",
      parameters: {
        type: "object",
        properties: {
          path: { type: "string", description: "Relative path" },
          content: { type: "string", description: "Complete file content" }
        },
        required: ["path", "content"]
      }
    }
  },
  {
    type: "function",
    function: {
      name: "patch_file",
      description: "Edit an existing file by replacing a unique block of text. Space-sensitive. Preferred over write_file.",
      parameters: {
        type: "object",
        properties: {
          path: { type: "string", description: "Relative path" },
          target: { type: "string", description: "Exact text block to replace (must match including indentation)" },
          replacement: { type: "string", description: "Replacement text with correct indentation" }
        },
        required: ["path", "target", "replacement"]
      }
    }
  },
  {
    type: "function",
    function: {
      name: "list_dir",
      description: "List directory contents. Skips node_modules and .git.",
      parameters: {
        type: "object",
        properties: {
          path: { type: "string", description: "Directory path" },
          recursive: { type: "boolean", description: "List recursively" }
        },
        required: ["path"]
      }
    }
  },
  {
    type: "function",
    function: {
      name: "run_command",
      description: "Execute a shell command. 30s timeout.",
      parameters: {
        type: "object",
        properties: {
          command: { type: "string", description: "Shell command" },
          cwd: { type: "string", description: "Working directory (relative)" }
        },
        required: ["command"]
      }
    }
  },
  {
    type: "function",
    function: {
      name: "grep_search",
      description: "Search for a pattern across files.",
      parameters: {
        type: "object",
        properties: {
          pattern: { type: "string", description: "Search pattern (regex)" },
          path: { type: "string", description: "Search directory" },
          include: { type: "string", description: "File glob filter (e.g. '*.js')" }
        },
        required: ["pattern", "path"]
      }
    }
  },
  {
    type: "function",
    function: {
      name: "index_codebase",
      description: "Scan the repo and generate .agent_index.json with file structure, exports, and imports. Run at task start.",
      parameters: { type: "object", properties: {} }
    }
  },
  {
    type: "function",
    function: {
      name: "peek_terminal",
      description: "Peek at the active background terminal process output buffer, check its status (running, completed), or terminate it.",
      parameters: {
        type: "object",
        properties: {
          action: { type: "string", enum: ["peek", "kill"], description: "Action to perform (default: 'peek')" }
        }
      }
    }
  },
  {
    type: "function",
    function: {
      name: "extend_deadline",
      description: "Extend the estimated task completion time limit. Use this if the task is taking longer than expected or needs additional complex phases.",
      parameters: {
        type: "object",
        properties: {
          additional_seconds: { type: "number", description: "Number of seconds to add to the deadline (e.g., 60, 120)" },
          reason: { type: "string", description: "Reason explaining why the deadline extension is required" }
        },
        required: ["additional_seconds", "reason"]
      }
    }
  },
  // ---- Dynamic Capability Tools (Modes-as-Tools) ----
  {
    type: "function",
    function: {
      name: "run_simulation",
      description: "Spawn isolated sandbox scenarios (git worktrees) to test 2–4 competing implementations of a task. Each scenario runs the full agent loop, the best result is automatically promoted to the live workspace. Use when you need to evaluate multiple approaches before committing. Returns the winning scenario's result.",
      parameters: {
        type: "object",
        properties: {
          task: { type: "string", description: "The specific coding task to simulate (be concrete and specific)" },
          reason: { type: "string", description: "Why sandbox simulation is needed for this step" }
        },
        required: ["task", "reason"]
      }
    }
  },
  {
    type: "function",
    function: {
      name: "spawn_subagents",
      description: "Decompose a wide task into parallel subtasks executed by independent subagents in isolated git worktrees. Results are automatically merged back into the main workspace. Use when work can be split into 2+ independent units (different files, different features, different modules).",
      parameters: {
        type: "object",
        properties: {
          subtasks: {
            type: "array",
            items: {
              type: "object",
              properties: {
                label: { type: "string", description: "Short identifier (e.g. 'auth-module', 'test-suite')" },
                description: { type: "string", description: "Full task description for this subagent — be specific and self-contained" }
              },
              required: ["label", "description"]
            },
            description: "List of independently executable subtasks (2–5 recommended)"
          },
          reason: { type: "string", description: "Why parallel decomposition is the right approach here" }
        },
        required: ["subtasks", "reason"]
      }
    }
  },
  {
    type: "function",
    function: {
      name: "delegate_to_director",
      description: "Escalate the current task to the Director AI for multi-cycle autonomous planning and supervision. Use when the task scope has grown beyond the current step budget, requires long-horizon orchestration, or needs iterative self-correction across many rounds.",
      parameters: {
        type: "object",
        properties: {
          goal: { type: "string", description: "The high-level goal to hand off to the Director — be comprehensive" },
          reason: { type: "string", description: "Why director escalation is the right approach" }
        },
        required: ["goal", "reason"]
      }
    }
  },
  // ---- Text-Only DOM Verifier ----
  {
    type: "function",
    function: {
      name: "verify_dom_state",
      description: "Fetch a running web app's HTML over HTTP and run deterministic text-based DOM assertions. No screenshots, no browser launch. Checks CSS classes, element IDs, text content, and attributes directly from the HTML source. Use this for ALL UI verification tasks.",
      parameters: {
        type: "object",
        properties: {
          url: { type: "string", description: "URL of the page to verify (e.g. http://localhost:3000)" },
          assertions: {
            type: "array",
            items: { type: "string" },
            description: "Assertions to check. Formats: 'text:Submit' (text present), 'not-text:Error' (text absent), 'class:dark' (CSS class present), 'element:#login-btn' (id present), 'element:.nav-item' (class present), 'element:header' (tag present), 'attr:data-theme=dark' (attribute=value)"
          }
        },
        required: ["url", "assertions"]
      }
    }
  },
  // ---- Git State Rewind ----
  {
    type: "function",
    function: {
      name: "rewind_to_checkpoint",
      description: "Rewind the workspace files to a previous step's git snapshot. Use this to undo a bad file change. Checkpoints are automatically created before every write_file, patch_file, or run_command call. The message context will also be rewound.",
      parameters: {
        type: "object",
        properties: {
          step: { type: "integer", description: "The step number to rewind to (checkpoints are created before each mutating tool call)" }
        },
        required: ["step"]
      }
    }
  }
];


