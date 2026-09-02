// ============================================================
// tools.js — Tool implementations (the agent's "hands")
// ============================================================

import { readFile, writeFile, mkdir, readdir, stat, appendFile } from "node:fs/promises";
import { exec, spawn } from "node:child_process";
import { resolve, relative, dirname, basename } from "node:path";
import { createInterface } from "node:readline";
import { existsSync } from "node:fs";
import { get as httpGet } from "node:http";
import { get as httpsGet } from "node:https";
import chalk from "chalk";
import { getSwadesCacheDir, ensureCacheDir } from "./cleanup.js";

// Dangerous command patterns that require user confirmation
const DANGEROUS_PATTERNS = [
  "rm -rf",
  "rm -r",
  "sudo ",
  "kill ",
  "mkfs",
  "> /dev/",
  "dd if=",
  "chmod 777",
  ":(){",
  "format ",
];

let activeBgProcess = null;
let activeBgPid = null;
let activeBgLogPath = null;

export let activeDeadline = {
  estimatedSeconds: 180,
  startTime: Date.now()
};

function isProcessAlive(pid) {
  if (!pid) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (e) {
    return false;
  }
}

// ---- Helpers ----

function getWorkdir() {
  const dir = process.env.WORKDIR || process.cwd();
  return existsSync(dir) ? dir : process.cwd();
}

function resolvePath(p) {
  if (!p) return getWorkdir();
  return resolve(getWorkdir(), p);
}

function truncate(str, maxLen) {
  // Do not truncate outputs — preserving complete context for the AI model and inspector
  const max = maxLen || parseInt(process.env.MAX_OUTPUT_LENGTH) || 100000;
  if (str.length <= max) return str;
  return str;
}

async function confirm(message) {
  if (process.env.AUTO_APPROVE === "true" || process.env.NON_INTERACTIVE === "true" || !process.stdin.isTTY) {
    return true;
  }
  const rl = createInterface({ input: process.stdin, output: process.stdout });
  return new Promise((res) => {
    rl.question(`${message} (y/N): `, (answer) => {
      rl.close();
      res(answer.toLowerCase() === "y");
    });
  });
}

// ---- Heuristic Syntax & Indentation Checker ----

function fixUnclosedBrackets(content) {
  const lines = content.split("\n");
  const brackets = { "{": "}", "(": ")", "[": "]" };
  const stack = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    let inString = false;
    let stringChar = "";
    for (let col = 0; col < line.length; col++) {
      const char = line[col];
      if ((char === '"' || char === "'" || char === "`") && line[col - 1] !== "\\") {
        if (!inString) {
          inString = true;
          stringChar = char;
        } else if (stringChar === char) {
          inString = false;
        }
      }
      if (!inString) {
        if (char === "{" || char === "(" || char === "[") {
          stack.push(char);
        } else if (char === "}" || char === ")" || char === "]") {
          stack.pop();
        }
      }
    }
  }
  if (stack.length > 0) {
    let appendStr = "";
    while (stack.length > 0) {
      const open = stack.pop();
      appendStr += brackets[open];
    }
    return content + (content.endsWith("\n") ? "" : "\n") + appendStr;
  }
  return content;
}

function fixJson(content) {
  let fixed = content;
  // 1. Remove trailing commas
  fixed = fixed.replace(/,(\s*[\]}])/g, "$1");
  // 2. Wrap unquoted keys in double quotes
  fixed = fixed.replace(/(?<={|,)\s*([a-zA-Z0-9_$]+)\s*:/g, '"$1":');
  // 3. Replace single quotes around keys/values with double quotes
  try {
    JSON.parse(fixed);
    return fixed;
  } catch (e) {
    let fixed2 = fixed.replace(/'([^']*)'/g, '"$1"');
    try {
      JSON.parse(fixed2);
      return fixed2;
    } catch (e2) {
      return fixed;
    }
  }
}

function fixMixedIndentation(content) {
  const lines = content.split("\n");
  let spaceLines = 0;
  let tabLines = 0;
  for (const line of lines) {
    const leading = line.match(/^([ \t]+)/);
    if (leading) {
      if (leading[1].includes(" ")) spaceLines++;
      if (leading[1].includes("\t")) tabLines++;
    }
  }
  if (spaceLines > 0 && tabLines > 0) {
    if (spaceLines >= tabLines) {
      return lines.map(line => {
        const leading = line.match(/^([ \t]+)/);
        if (leading) {
          const cleanLeading = leading[1].replace(/\t/g, "    ");
          return cleanLeading + line.slice(leading[0].length);
        }
        return line;
      }).join("\n");
    } else {
      return lines.map(line => {
        const leading = line.match(/^([ \t]+)/);
        if (leading) {
          const cleanLeading = leading[1].replace(/    /g, "\t").replace(/  /g, "\t");
          return cleanLeading + line.slice(leading[0].length);
        }
        return line;
      }).join("\n");
    }
  }
  return content;
}

function checkSyntaxAndIndentation(filePath, content) {
  const ext = filePath.split(".").pop().toLowerCase();
  const errors = [];
  const warnings = [];
  const lines = content.split("\n");

  const isIndentationSensitive = ["py", "yml", "yaml", "gd", "nim", "hs"].includes(ext);

  if (isIndentationSensitive) {
    // 1. Indentation mix check (spaces vs tabs) & Indentation jump check
    let hasSpaces = false;
    let hasTabs = false;
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      const leading = line.match(/^([ \t]+)/);
      if (leading) {
        if (leading[1].includes(" ")) hasSpaces = true;
        if (leading[1].includes("\t")) hasTabs = true;

        // Indentation jump checks (spaces only for simplicity)
        if (hasSpaces && !hasTabs) {
          const spaceCount = leading[1].length;
          if (i > 0) {
            const prevLine = lines[i - 1];
            const prevLeading = prevLine.match(/^([ ]+)/);
            if (prevLeading) {
              const prevCount = prevLeading[1].length;
              const diff = spaceCount - prevCount;
              // Alert on sudden jumps greater than 4 spaces without brace/colon opening
              if (
                diff > 4 &&
                !prevLine.trim().endsWith("{") &&
                !prevLine.trim().endsWith(":") &&
                !prevLine.trim().endsWith("(") &&
                !prevLine.trim().endsWith("[")
              ) {
                warnings.push(`Line ${i + 1}: Indentation jumped suddenly by ${diff} spaces without a block opening character ({, :, (, [).`);
              }
            }
          }
        }
      }
    }

    if (hasSpaces && hasTabs) {
      warnings.push("Mixed spaces and tabs detected in file indentation. Use either spaces or tabs consistently.");
    }
  }

  // 2. Bracket matching checks (curly braces, parentheses, square brackets)
  const brackets = {
    "{": "}",
    "(": ")",
    "[": "]",
  };
  const stack = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    let inString = false;
    let stringChar = "";
    
    for (let col = 0; col < line.length; col++) {
      const char = line[col];
      // Skip strings to avoid matching quotes/braces inside literals
      if ((char === '"' || char === "'" || char === "`") && line[col - 1] !== "\\") {
        if (!inString) {
          inString = true;
          stringChar = char;
        } else if (stringChar === char) {
          inString = false;
        }
      }

      if (!inString) {
        if (char === "{" || char === "(" || char === "[") {
          stack.push({ char, line: i + 1, col: col + 1 });
        } else if (char === "}" || char === ")" || char === "]") {
          const last = stack.pop();
          if (!last) {
            errors.push(`Unmatched closing bracket '${char}' at line ${i + 1}:${col + 1}`);
          } else if (brackets[last.char] !== char) {
            errors.push(`Mismatched bracket: expected '${brackets[last.char]}' for '${last.char}' from line ${last.line}:${last.col}, but found '${char}' at line ${i + 1}:${col + 1}`);
          }
        }
      }
    }
  }

  while (stack.length > 0) {
    const unclosed = stack.pop();
    errors.push(`Unclosed bracket '${unclosed.char}' opened at line ${unclosed.line}:${unclosed.col}`);
  }

  return { errors, warnings };
}

// Perform active checks (Node check for JS, JSON.parse for JSON, py_compile for Python) and auto-fix if needed
async function performPostWriteValidation(fullPath, content) {
  const ext = fullPath.split(".").pop().toLowerCase();
  
  // 1. Run initial checks
  let heuristics = checkSyntaxAndIndentation(fullPath, content);
  let isJsonValid = true;
  if (ext === "json") {
    try {
      JSON.parse(content);
    } catch (err) {
      isJsonValid = false;
      heuristics.errors.push(`JSON Parsing Error: ${err.message}`);
    }
  }

  // 2. If errors/warnings detected, try to auto-fix
  if (heuristics.errors.length > 0 || heuristics.warnings.length > 0) {
    let fixedContent = content;
    let didChange = false;

    // Apply JSON fixes if needed
    if (ext === "json" && !isJsonValid) {
      const maybeFixed = fixJson(content);
      if (maybeFixed !== content) {
        fixedContent = maybeFixed;
        didChange = true;
      }
    }

    // Apply bracket fixes for JS/JSON etc if unclosed brackets exist
    const hasUnclosedBracket = heuristics.errors.some(e => e.includes("Unclosed bracket"));
    if (hasUnclosedBracket && ["js", "json", "ts", "jsx", "tsx", "css", "html"].includes(ext)) {
      const maybeFixed = fixUnclosedBrackets(fixedContent);
      if (maybeFixed !== fixedContent) {
        fixedContent = maybeFixed;
        didChange = true;
      }
    }

    // Apply indentation fixes for mixed indentation
    const hasMixedIndentation = heuristics.warnings.some(w => w.includes("Mixed spaces and tabs"));
    if (hasMixedIndentation) {
      const maybeFixed = fixMixedIndentation(fixedContent);
      if (maybeFixed !== fixedContent) {
        fixedContent = maybeFixed;
        didChange = true;
      }
    }

    // 3. If we updated the content, write it back and re-run checks
    if (didChange) {
      try {
        await writeFile(fullPath, fixedContent, "utf-8");
        // Recheck
        heuristics = checkSyntaxAndIndentation(fullPath, fixedContent);
        if (ext === "json") {
          try {
            JSON.parse(fixedContent);
          } catch (err) {
            heuristics.errors.push(`JSON Parsing Error (post-fix): ${err.message}`);
          }
        }
        heuristics.autoFixed = true;
      } catch (err) {
        heuristics.errors.push(`Auto-fix write error: ${err.message}`);
      }
    }
  }

  // Node check for JS files
  if (ext === "js" || ext === "mjs" || ext === "cjs") {
    // Read the current file on disk (it might have been auto-fixed)
    let currentContent = content;
    try {
      currentContent = await readFile(fullPath, "utf-8");
    } catch (readErr) {
      console.log(chalk.dim(`   ⚠ Post-validation re-read failed: ${readErr.message}`));
    }

    const errorMsg = await new Promise((res) => {
      exec(`node --check "${fullPath}"`, (err, stdout, stderr) => {
        if (err) res(stderr.trim() || err.message);
        else res(null);
      });
    });
    if (errorMsg) {
      // If we haven't tried fixing unclosed brackets yet, let's try it
      const hasUnclosedBracket = errorMsg.includes("missing }") || errorMsg.includes("unexpected end of input") || errorMsg.includes("missing )") || errorMsg.includes("missing ]");
      if (hasUnclosedBracket && !heuristics.autoFixed) {
        const maybeFixed = fixUnclosedBrackets(currentContent);
        if (maybeFixed !== currentContent) {
          try {
            await writeFile(fullPath, maybeFixed, "utf-8");
            const secondCheckError = await new Promise((res) => {
              exec(`node --check "${fullPath}"`, (err, stdout, stderr) => {
                if (err) res(stderr.trim() || err.message);
                else res(null);
              });
            });
            if (!secondCheckError) {
              heuristics.autoFixed = true;
              // Clear previous JS/Node syntax errors
              heuristics.errors = heuristics.errors.filter(e => !e.includes("Node.js Syntax Error"));
            } else {
              heuristics.errors.push(`Node.js Syntax Error (post-fix):\n${secondCheckError}`);
            }
          } catch (writeErr) {
            heuristics.errors.push(`Auto-fix write error: ${writeErr.message}`);
          }
        } else {
          heuristics.errors.push(`Node.js Syntax Error:\n${errorMsg}`);
        }
      } else {
        heuristics.errors.push(`Node.js Syntax Error:\n${errorMsg}`);
      }
    }
  }

  // Python syntax check for .py files
  if (ext === "py") {
    const pyError = await new Promise((res) => {
      exec(`python3 -m py_compile "${fullPath}" 2>&1 || python -m py_compile "${fullPath}" 2>&1`, (err, stdout, stderr) => {
        if (err) res((stderr || stdout || err.message).trim());
        else res(null);
      });
    });
    if (pyError && !pyError.includes("No module named") && !pyError.includes("not found")) {
      heuristics.errors.push(`Python Syntax Error:\n${pyError}`);
    }
  }

  return heuristics;
}

// ---- Codebase Indexing Engine (now writes to cache dir) ----

function parseFileStructure(filename, content) {
  const ext = filename.split(".").pop().toLowerCase();
  const structure = {
    imports: [],
    exports: [],
    classes: [],
    functions: [],
  };

  const lines = content.split("\n");

  if (["js", "mjs", "cjs", "ts", "tsx", "jsx"].includes(ext)) {
    for (const line of lines) {
      // Parse imports
      const importMatches = [...line.matchAll(/import\s+.*\s+from\s+['"](.*)[''"]/g)];
      for (const m of importMatches) structure.imports.push(m[1]);

      // Parse classes
      const classMatches = [...line.matchAll(/class\s+(\w+)/g)];
      for (const m of classMatches) structure.classes.push(m[1]);

      // Parse functions
      const funcMatches = [...line.matchAll(/(?:function\s+(\w+)|const\s+(\w+)\s*=\s*\([^)]*\)\s*=>)/g)];
      for (const m of funcMatches) structure.functions.push(m[1] || m[2]);

      // Parse exports
      const exportMatches = [...line.matchAll(/export\s+(?:default\s+)?(?:const|class|function|let|var)?\s*(\w+)/g)];
      for (const m of exportMatches) {
        if (m[1] && !["const", "class", "function", "let", "var", "default"].includes(m[1])) {
          structure.exports.push(m[1]);
        }
      }
    }
  } else if (ext === "py") {
    for (const line of lines) {
      const classMatch = line.match(/^class\s+(\w+)/);
      if (classMatch) structure.classes.push(classMatch[1]);

      const defMatch = line.match(/^\s*def\s+(\w+)/);
      if (defMatch) structure.functions.push(defMatch[1]);
    }
  }

  // Deduplicate and filter empty strings
  structure.imports = [...new Set(structure.imports)].filter(Boolean);
  structure.exports = [...new Set(structure.exports)].filter(Boolean);
  structure.classes = [...new Set(structure.classes)].filter(Boolean);
  structure.functions = [...new Set(structure.functions)].filter(Boolean);

  return structure;
}

async function generateCodebaseIndex() {
  const workdir = getWorkdir();
  const cacheDir = await ensureCacheDir(workdir);

  const index = {
    generatedAt: new Date().toISOString(),
    workdir,
    files: {},
  };

  async function scan(dir) {
    let items;
    try {
      items = await readdir(dir, { withFileTypes: true });
    } catch (err) {
      console.log(chalk.dim(`   ⚠ Cannot read directory ${dir}: ${err.message}`));
      return;
    }

    for (const item of items) {
      if (
        item.name === "node_modules" ||
        item.name === ".git" ||
        item.name === ".agent_index.json" ||
        item.name === ".agent_memory.json" ||
        item.name === ".swades_worktrees" ||
        item.name === ".swades_sandboxes"
      ) {
        continue;
      }
      const fullPath = resolve(dir, item.name);
      const relPath = relative(workdir, fullPath);

      if (item.isDirectory()) {
        await scan(fullPath);
      } else {
        const info = await stat(fullPath);
        // Only index text-like source files under 1MB
        const ext = item.name.split(".").pop().toLowerCase();
        const textExtensions = ["js", "jsx", "ts", "tsx", "py", "json", "html", "css", "md", "sh", "yml", "yaml", "env"];
        
        if (info.size < 1024 * 1024 && textExtensions.includes(ext)) {
          try {
            const content = await readFile(fullPath, "utf-8");
            const structure = parseFileStructure(item.name, content);
            index.files[relPath] = {
              size: info.size,
              structure,
            };
          } catch (readErr) {
            console.log(chalk.dim(`   ⚠ Cannot read file ${relPath}: ${readErr.message}`));
          }
        }
      }
    }
  }

  await scan(workdir);

  // Write index to cache directory instead of project root
  const indexPath = resolve(cacheDir, "agent_index.json");
  await writeFile(indexPath, JSON.stringify(index, null, 2), "utf-8");
  return index;
}

// ---- Stack Detection Engine ----

/**
 * Detect the project's technology stack by scanning for indicator files.
 * Returns a structured object describing the detected runtime, framework, and language.
 *
 * @param {string} workdir - Absolute path to the workspace root
 * @returns {{ language: string, runtime: string, framework: string, packageManager: string, details: string[] }}
 */
export async function detectProjectStack(workdir) {
  const stack = {
    language: "unknown",
    runtime: "unknown",
    framework: "none",
    packageManager: "none",
    details: [],
  };

  const dir = workdir || getWorkdir();

  // ---- JavaScript / TypeScript ----
  const pkgJsonPath = resolve(dir, "package.json");
  if (existsSync(pkgJsonPath)) {
    stack.language = "javascript";
    stack.runtime = "node";
    stack.packageManager = existsSync(resolve(dir, "yarn.lock")) ? "yarn" :
                           existsSync(resolve(dir, "pnpm-lock.yaml")) ? "pnpm" : "npm";
    stack.details.push("package.json detected");

    try {
      const pkg = JSON.parse(await readFile(pkgJsonPath, "utf-8"));
      const allDeps = { ...pkg.dependencies, ...pkg.devDependencies };

      // Detect frameworks
      if (allDeps["next"]) { stack.framework = "next.js"; stack.details.push("Next.js framework"); }
      else if (allDeps["react"]) { stack.framework = "react"; stack.details.push("React library"); }
      else if (allDeps["vue"]) { stack.framework = "vue"; stack.details.push("Vue.js framework"); }
      else if (allDeps["svelte"]) { stack.framework = "svelte"; stack.details.push("Svelte framework"); }
      else if (allDeps["express"]) { stack.framework = "express"; stack.details.push("Express.js server"); }
      else if (allDeps["fastify"]) { stack.framework = "fastify"; stack.details.push("Fastify server"); }
      else if (allDeps["hono"]) { stack.framework = "hono"; stack.details.push("Hono framework"); }

      // Detect TypeScript
      if (allDeps["typescript"] || existsSync(resolve(dir, "tsconfig.json"))) {
        stack.language = "typescript";
        stack.details.push("TypeScript detected");
      }

      // Detect if it's a VS Code extension
      if (pkg.engines?.vscode) {
        stack.details.push("VS Code extension");
      }

      // Detect if it's a CLI tool
      if (pkg.bin) {
        stack.details.push("CLI tool (has bin entry)");
      }

      // Detect Cloudflare Workers / Edge
      if (allDeps["wrangler"] || allDeps["@cloudflare/workers-types"]) {
        stack.runtime = "cloudflare-workers";
        stack.details.push("Cloudflare Workers runtime");
      }
    } catch (readErr) {
      stack.details.push(`package.json parse error: ${readErr.message}`);
    }
  }

  // ---- Python ----
  if (existsSync(resolve(dir, "requirements.txt")) || existsSync(resolve(dir, "pyproject.toml")) || existsSync(resolve(dir, "setup.py"))) {
    stack.language = stack.language === "unknown" ? "python" : stack.language;
    stack.runtime = stack.runtime === "unknown" ? "python" : stack.runtime;
    stack.details.push("Python project detected");

    if (existsSync(resolve(dir, "pyproject.toml"))) {
      stack.packageManager = "poetry/pip";
      stack.details.push("pyproject.toml found");
    }
    if (existsSync(resolve(dir, "Pipfile"))) {
      stack.packageManager = "pipenv";
      stack.details.push("Pipfile found");
    }
  }

  // ---- Rust ----
  if (existsSync(resolve(dir, "Cargo.toml"))) {
    stack.language = "rust";
    stack.runtime = "native";
    stack.packageManager = "cargo";
    stack.details.push("Rust project (Cargo.toml)");
  }

  // ---- Go ----
  if (existsSync(resolve(dir, "go.mod"))) {
    stack.language = "go";
    stack.runtime = "native";
    stack.packageManager = "go modules";
    stack.details.push("Go project (go.mod)");
  }

  // ---- Java / Kotlin / Gradle ----
  if (existsSync(resolve(dir, "build.gradle")) || existsSync(resolve(dir, "build.gradle.kts")) || existsSync(resolve(dir, "pom.xml"))) {
    stack.language = stack.language === "unknown" ? "java" : stack.language;
    stack.runtime = "jvm";
    stack.packageManager = existsSync(resolve(dir, "pom.xml")) ? "maven" : "gradle";
    stack.details.push("JVM project detected");
  }

  return stack;
}

// ---- Tool Implementations ----

async function readFileTool({ path, start_line, end_line }) {
  const fullPath = resolvePath(path);
  const content = await readFile(fullPath, "utf-8");

  if (start_line || end_line) {
    const lines = content.split("\n");
    const start = (start_line || 1) - 1;
    const end = end_line || lines.length;
    const sliced = lines.slice(start, end);
    return sliced.map((line, i) => `${start + i + 1} | ${line}`).join("\n");
  }

  // Add line numbers
  return content
    .split("\n")
    .map((line, i) => `${i + 1} | ${line}`)
    .join("\n");
}

async function writeFileTool({ path, content }) {
  const fullPath = resolvePath(path);
  await mkdir(dirname(fullPath), { recursive: true });
  
  // Write content first
  await writeFile(fullPath, content, "utf-8");

  // Validate syntax and indentation
  const validation = await performPostWriteValidation(fullPath, content);
  
  // Incremental index update (non-blocking)
  _updateIndexForFile(fullPath, content).catch(() => {});

  let report = `✅ File written successfully: ${path} (${content.length} bytes)`;
  if (validation.errors.length > 0) {
    report += `\n\n❌ WARNING: SYNTAX ERRORS DETECTED:\n- ` + validation.errors.join("\n- ");
  }
  if (validation.warnings.length > 0) {
    report += `\n\n⚠️ INDENTATION WARNINGS:\n- ` + validation.warnings.join("\n- ");
  }
  return report;
}

async function patchFileTool({ path, target, replacement }) {
  const fullPath = resolvePath(path);
  if (!existsSync(fullPath)) {
    return `❌ Error: File does not exist at path: ${path}. Use write_file to create new files.`;
  }

  const content = await readFile(fullPath, "utf-8");
  
  // Normalize line endings and trim trailing spaces for robust matching
  const normalize = (str) => str.replace(/\r\n/g, "\n").replace(/[ \t]+$/gm, "");
  const normalizedContent = normalize(content);
  const normalizedTarget = normalize(target);
  
  const occurrences = normalizedContent.split(normalizedTarget).length - 1;
  
  if (occurrences === 0) {
    return `❌ Error: Target block not found in the file. Ensure your 'target' content matches the file EXACTLY (including indentation and casing).`;
  }
  if (occurrences > 1) {
    return `❌ Error: Multiple matches (${occurrences}) of the target block were found. Provide more surrounding lines (context) to make the target block unique.`;
  }

  // Perform single replacement using split/join to avoid '$' replacement pattern expansion
  const parts = normalizedContent.split(normalizedTarget);
  const newContent = parts.join(normalize(replacement));
  
  // Write to disk
  await writeFile(fullPath, newContent, "utf-8");

  // Incremental index update (non-blocking)
  _updateIndexForFile(fullPath, newContent).catch(() => {});

  // Validate syntax and indentation
  const validation = await performPostWriteValidation(fullPath, newContent);
  
  let report = `✅ File patched successfully: ${path}`;
  if (validation.errors.length > 0) {
    report += `\n\n❌ WARNING: SYNTAX ERRORS DETECTED IN THE NEW PATCH:\n- ` + validation.errors.join("\n- ");
  }
  if (validation.warnings.length > 0) {
    report += `\n\n⚠️ INDENTATION WARNINGS DETECTED IN THE NEW PATCH:\n- ` + validation.warnings.join("\n- ");
  }
  return report;
}

async function listDirTool({ path, recursive }) {
  const fullPath = resolvePath(path);
  const entries = [];
  const agentRoot = process.cwd(); // The agent's own root folder

  async function walk(dir, depth = 0) {
    const items = await readdir(dir, { withFileTypes: true });
    for (const item of items) {
      // Skip node_modules and .git
      if (item.name === "node_modules" || item.name === ".git") continue;

      const itemPath = resolve(dir, item.name);

      // Skip the agent's own installation folder to prevent the LLM from getting trapped/distracted
      // Only apply this skip if the agent is installed in a strict subdirectory of the workspace
      const isStrictSubDir = agentRoot.startsWith(fullPath + "/") || (fullPath !== agentRoot && agentRoot.startsWith(fullPath));
      if (isStrictSubDir && (itemPath === agentRoot || itemPath.startsWith(agentRoot + "/"))) {
        continue;
      }

      const rel = relative(fullPath, itemPath);
      const prefix = "  ".repeat(depth);
      const isDir = item.isDirectory();

      if (isDir) {
        entries.push(`${prefix}📁 ${rel}/`);
        if (recursive) await walk(itemPath, depth + 1);
      } else {
        const info = await stat(itemPath);
        const size = info.size;
        const sizeStr =
          size > 1024
            ? `${(size / 1024).toFixed(1)}KB`
            : `${size}B`;
        entries.push(`${prefix}📄 ${rel} (${sizeStr})`);
      }
    }
  }

  await walk(fullPath);
  return entries.length > 0 ? entries.join("\n") : "(empty directory)";
}

async function runCommandTool({ command, cwd }) {
  let workdir = cwd ? resolvePath(cwd) : getWorkdir();
  if (!existsSync(workdir)) {
    workdir = process.cwd();
  }

  // Safety check for dangerous commands
  const isDangerous = DANGEROUS_PATTERNS.some((p) =>
    command.toLowerCase().includes(p.toLowerCase())
  );
  if (isDangerous) {
    const allowed = await confirm(
      `⚠️  Potentially dangerous command:\n   ${command}\n   Allow execution?`
    );
    if (!allowed) return "❌ Command blocked by user.";
  }

  // Check if a background command is already active
  if (activeBgPid && isProcessAlive(activeBgPid)) {
    return `⚠️ A background process is already running (PID ${activeBgPid}). Use 'peek_terminal' to check its progress, or run 'peek_terminal' with action='kill' to terminate it first.`;
  }

  // Write terminal log to cache dir instead of project root
  const cacheDir = await ensureCacheDir(getWorkdir());
  activeBgLogPath = resolve(cacheDir, "agent_terminal.log");

  try {
    await writeFile(activeBgLogPath, `--- Run Command: ${command} ---\n`, "utf-8");
  } catch (err) {
    return `❌ Failed to initialize log file: ${err.message}`;
  }

  const child = spawn(command, {
    shell: true,
    cwd: workdir,
    detached: true,
    stdio: ["ignore", "pipe", "pipe"]
  });

  activeBgProcess = child;
  activeBgPid = child.pid;

  child.stdout.on("data", (data) => {
    appendFile(activeBgLogPath, data).catch((appendErr) => {
      console.log(chalk.dim(`   ⚠ Log append error: ${appendErr.message}`));
    });
  });

  child.stderr.on("data", (data) => {
    appendFile(activeBgLogPath, data).catch((appendErr) => {
      console.log(chalk.dim(`   ⚠ Log append error: ${appendErr.message}`));
    });
  });

  let exitCode = null;
  let hasExited = false;

  child.on("exit", (code) => {
    exitCode = code;
    hasExited = true;
    activeBgProcess = null;
    activeBgPid = null;
  });

  child.on("error", (err) => {
    appendFile(activeBgLogPath, `\nERROR SPAWNING PROCESS: ${err.message}\n`).catch((appendErr) => {
      console.log(chalk.dim(`   ⚠ Error log append failed: ${appendErr.message}`));
    });
    hasExited = true;
    activeBgProcess = null;
    activeBgPid = null;
  });

  const timeoutMs = 30000;
  
  return new Promise((resolvePromise) => {
    const checkInterval = setInterval(async () => {
      if (hasExited) {
        clearInterval(checkInterval);
        clearTimeout(timer);
        try {
          const logContent = await readFile(activeBgLogPath, "utf-8");
          let output = logContent;
          if (exitCode !== null && exitCode !== 0) {
            output += `\nCommand exited with code ${exitCode}`;
          }
          resolvePromise(truncate(output || "(no output)"));
        } catch (e) {
          resolvePromise(`Command completed but failed to read output: ${e.message}`);
        }
      }
    }, 100);

    const timer = setTimeout(async () => {
      clearInterval(checkInterval);
      try {
        const logContent = await readFile(activeBgLogPath, "utf-8");
        resolvePromise(`⚠️ [TIMEOUT] The command is taking longer than 30s. It has been detached and is running in the background.
You can monitor the output using the 'peek_terminal' tool.
Recent output:
${truncate(logContent || "(no output)")}`);
      } catch (e) {
        resolvePromise(`⚠️ [TIMEOUT] The command is taking longer than 30s. It has been detached. Failed to read current logs: ${e.message}`);
      }
    }, timeoutMs);
  });
}

async function peekTerminalTool({ action = "peek" } = {}) {
  if (action === "kill") {
    if (!activeBgPid) {
      return "❌ No active background process to kill.";
    }
    try {
      process.kill(-activeBgPid, "SIGTERM");
    } catch (e) {
      try {
        process.kill(activeBgPid, "SIGTERM");
      } catch (e2) {
        return `❌ Failed to kill process: ${e2.message}`;
      }
    }
    activeBgProcess = null;
    activeBgPid = null;
    return "✅ Sent SIGTERM to the active background process.";
  }

  // Check cache dir for log file
  const cacheDir = getSwadesCacheDir(getWorkdir());
  const logPath = resolve(cacheDir, "agent_terminal.log");
  const logExists = existsSync(logPath);

  if (!activeBgPid) {
    if (logExists) {
      try {
        const logContent = await readFile(logPath, "utf-8");
        return `[STATUS: INACTIVE] No background process is active.
Last process output:
${truncate(logContent || "(no output)")}`;
      } catch (e) {
        return `[STATUS: INACTIVE] No background process is active. Failed to read logs: ${e.message}`;
      }
    }
    return `[STATUS: INACTIVE] No background process has been run yet.`;
  }

  const alive = isProcessAlive(activeBgPid);
  let logContent = "";
  if (logExists) {
    try {
      logContent = await readFile(logPath, "utf-8");
    } catch (e) {
      logContent = `Error reading terminal buffer: ${e.message}`;
    }
  }

  if (alive) {
    return `[STATUS: RUNNING] Process is still executing in the background (PID ${activeBgPid}).
Recent output:
${truncate(logContent || "(no output)")}`;
  } else {
    activeBgProcess = null;
    activeBgPid = null;
    return `[STATUS: COMPLETED] The process has finished running.
Final output:
${truncate(logContent || "(no output)")}`;
  }
}

async function grepSearchTool({ pattern, path, include }) {
  const fullPath = resolvePath(path);
  const agentRoot = process.cwd();

  // Build grep command
  let cmd = `grep -rnI --color=never`;
  if (include) cmd += ` --include='${include}'`;

  // Exclude the agent folder if it lies inside the search path
  if (agentRoot.startsWith(fullPath)) {
    const relAgentFolder = relative(fullPath, agentRoot);
    if (relAgentFolder && !relAgentFolder.startsWith("..")) {
      cmd += ` --exclude-dir='${relAgentFolder}'`;
    }
  }

  cmd += ` '${pattern.replace(/'/g, "'\\''")}' '${fullPath}'`;

  return new Promise((res) => {
    exec(cmd, { maxBuffer: 1024 * 1024 }, (error, stdout) => {
      if (error && !stdout) {
        return res("No matches found.");
      }
      // Make paths relative for readability
      const result = stdout.replace(new RegExp(fullPath + "/", "g"), "");
      res(truncate(result || "No matches found."));
    });
  });
}

async function indexCodebaseTool() {
  try {
    const index = await generateCodebaseIndex();
    const fileCount = Object.keys(index.files).length;
    const cacheDir = getSwadesCacheDir(getWorkdir());
    return `✅ Codebase indexed successfully. Found and indexed ${fileCount} source files. Index saved to cache: ${cacheDir}/agent_index.json`;
  } catch (err) {
    return `❌ Error generating codebase index: ${err.message}`;
  }
}

async function extendDeadlineTool({ additional_seconds, reason }) {
  if (typeof additional_seconds !== "number" || additional_seconds <= 0) {
    return "❌ Error: 'additional_seconds' must be a positive number.";
  }
  activeDeadline.estimatedSeconds += additional_seconds;
  return `✅ Deadline successfully extended by ${additional_seconds} seconds. New limit: ${activeDeadline.estimatedSeconds}s. Reason: ${reason}`;
}

// ---- Incremental Index Update Helper ----

/**
 * Update only the changed file's entry in the existing codebase index.
 * Called non-blocking after write_file / patch_file to keep the index current.
 */
async function _updateIndexForFile(fullPath, content) {
  try {
    const workdir = getWorkdir();
    const cacheDir = getSwadesCacheDir(workdir);
    const indexPath = resolve(cacheDir, "agent_index.json");
    if (!existsSync(indexPath)) return;
    const index = JSON.parse(await readFile(indexPath, "utf-8"));
    const relPath = relative(workdir, fullPath);
    const structure = parseFileStructure(basename(fullPath), content);
    index.files[relPath] = { size: content.length, structure };
    index.lastUpdated = new Date().toISOString();
    await writeFile(indexPath, JSON.stringify(index, null, 2), "utf-8");
  } catch { /* non-fatal — full re-index will fix any inconsistency */ }
}

// ============================================================
// Dynamic Capability Tools — Modes-as-Tools
// These allow the agent to invoke simulation, subagents, and
// director escalation mid-flight without CLI flags.
// ============================================================

// Recursion depth guard — prevents runaway nesting (e.g., subagent spawning subagents)
function _checkRecursionDepth(toolName) {
  const depth = parseInt(process.env._SWADES_TOOL_DEPTH || "0");
  if (depth >= 2) {
    return `❌ [RECURSION GUARD] Cannot call '${toolName}' from within a subagent or simulation context (depth=${depth}). Complete this subtask directly with the available file tools.`;
  }
  return null;
}

function _incrementDepth() {
  const depth = parseInt(process.env._SWADES_TOOL_DEPTH || "0");
  process.env._SWADES_TOOL_DEPTH = String(depth + 1);
}

function _decrementDepth() {
  const depth = parseInt(process.env._SWADES_TOOL_DEPTH || "0");
  process.env._SWADES_TOOL_DEPTH = String(Math.max(0, depth - 1));
}

/**
 * run_simulation — spawn sandbox scenarios for the given task and promote the winner.
 */
async function runSimulationTool({ task, reason }) {
  const guard = _checkRecursionDepth("run_simulation");
  if (guard) return guard;

  console.log(chalk.magenta.bold(`\n🧪 [Tool] run_simulation triggered`));
  console.log(chalk.dim(`   Reason: ${reason}`));

  // Lazy import to avoid circular dependency at module load time
  const { runSimulated } = await import("./simulator.js");
  const workdir = getWorkdir();

  _incrementDepth();
  try {
    const result = await runSimulated(task, workdir);
    return `✅ Simulation complete: ${result}`;
  } catch (err) {
    return `❌ Simulation failed: ${err.message}`;
  } finally {
    _decrementDepth();
  }
}

/**
 * spawn_subagents — decompose a wide task into parallel subtasks in isolated worktrees.
 */
async function spawnSubagentsTool({ subtasks, reason }) {
  const guard = _checkRecursionDepth("spawn_subagents");
  if (guard) return guard;

  if (!Array.isArray(subtasks) || subtasks.length === 0) {
    return "❌ Error: 'subtasks' must be a non-empty array of {label, description} objects.";
  }

  console.log(chalk.cyan.bold(`\n🔷 [Tool] spawn_subagents triggered (${subtasks.length} subtasks)`));
  console.log(chalk.dim(`   Reason: ${reason}`));

  // Lazy imports
  const { runSubagentsParallel } = await import("./subagent.js");
  const { mergeDiffs } = await import("./orchestrator.js");
  const workdir = getWorkdir();

  _incrementDepth();
  try {
    const results = await runSubagentsParallel(subtasks, workdir);
    const mergeResult = await mergeDiffs(results, workdir);
    const passed = results.filter(r => r.success).length;
    return [
      `✅ Subagents complete: ${passed}/${results.length} succeeded.`,
      `   Merge: ${mergeResult.merged} applied, ${mergeResult.failed} failed.`,
      ...results.map(r => `   [${r.label}] ${r.success ? "✅" : "❌"} ${r.summary.slice(0, 120)}`),
    ].join("\n");
  } catch (err) {
    return `❌ Subagent spawning failed: ${err.message}`;
  } finally {
    _decrementDepth();
  }
}

/**
 * delegate_to_director — escalate to Director AI for multi-cycle autonomous planning.
 */
async function delegateToDirectorTool({ goal, reason }) {
  const guard = _checkRecursionDepth("delegate_to_director");
  if (guard) return guard;

  console.log(chalk.green.bold(`\n🎬 [Tool] delegate_to_director triggered`));
  console.log(chalk.dim(`   Reason: ${reason}`));
  console.log(chalk.dim(`   Goal: ${goal.slice(0, 120)}...`));

  const { runDirector } = await import("./director.js");

  _incrementDepth();
  try {
    const result = await runDirector(goal, Infinity);
    return `✅ Director completed: ${result.slice(0, 500)}`;
  } catch (err) {
    return `❌ Director escalation failed: ${err.message}`;
  } finally {
    _decrementDepth();
  }
}

// ============================================================
// Text-Only DOM Verification Tool
// Fetches HTML over node:http/https and runs text assertions.
// Zero external dependencies.
// ============================================================

/**
 * verify_dom_state — fetch a URL and run deterministic text-based DOM assertions.
 * Assertion formats:
 *   'class:dark'          → checks <html class> or any tag contains 'dark'
 *   'text:Submit'         → checks raw HTML contains 'Submit'
 *   'element:#login-btn'  → checks for id="login-btn"
 *   'attr:data-theme=dark' → checks for data-theme="dark"
 *   'not-text:Error'      → asserts 'Error' does NOT appear
 */
async function verifyDomStateTool({ url, assertions }) {
  if (!url) return "❌ Error: 'url' is required.";
  if (!Array.isArray(assertions) || assertions.length === 0) {
    return "❌ Error: 'assertions' must be a non-empty array.";
  }

  // Fetch the page HTML
  let html;
  try {
    html = await new Promise((res, rej) => {
      const getter = url.startsWith("https") ? httpsGet : httpGet;
      const req = getter(url, { timeout: 10000 }, (response) => {
        if (response.statusCode >= 300 && response.statusCode < 400 && response.headers.location) {
          // Single-level redirect follow
          const redirect = response.headers.location;
          const getter2 = redirect.startsWith("https") ? httpsGet : httpGet;
          getter2(redirect, { timeout: 10000 }, (r2) => {
            let data2 = "";
            r2.on("data", c => { data2 += c; });
            r2.on("end", () => res(data2));
            r2.on("error", rej);
          }).on("error", rej);
          return;
        }
        let data = "";
        response.on("data", chunk => { data += chunk; });
        response.on("end", () => res(data));
        response.on("error", rej);
      });
      req.on("error", rej);
      req.on("timeout", () => { req.destroy(); rej(new Error("Request timed out after 10s")); });
    });
  } catch (err) {
    return `❌ Failed to fetch ${url}: ${err.message}`;
  }

  const results = [];
  let passed = 0;
  let failed = 0;

  for (const assertion of assertions) {
    const [type, ...rest] = assertion.split(":");
    const value = rest.join(":").trim();
    let ok = false;
    let detail = "";

    switch (type.toLowerCase()) {
      case "text":
        ok = html.includes(value);
        detail = ok ? `Found '${value}' in HTML` : `'${value}' NOT found in HTML`;
        break;
      case "not-text":
        ok = !html.includes(value);
        detail = ok ? `Confirmed '${value}' absent from HTML` : `'${value}' unexpectedly present in HTML`;
        break;
      case "class": {
        // Check for the class anywhere in the HTML (works for <html class="dark"> etc.)
        const classRegex = new RegExp(`class=["'][^"']*\\b${value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b[^"']*["']`);
        ok = classRegex.test(html);
        detail = ok ? `Class '${value}' found` : `Class '${value}' NOT found`;
        break;
      }
      case "element": {
        // Support #id, .class, or tag selectors as text heuristics
        if (value.startsWith("#")) {
          const id = value.slice(1);
          ok = html.includes(`id="${id}"`) || html.includes(`id='${id}'`);
          detail = ok ? `Element id='${id}' found` : `Element id='${id}' NOT found`;
        } else if (value.startsWith(".")) {
          const cls = value.slice(1);
          const re = new RegExp(`class=["'][^"']*\\b${cls}\\b[^"']*["']`);
          ok = re.test(html);
          detail = ok ? `Element class='${cls}' found` : `Element class='${cls}' NOT found`;
        } else {
          // Tag check
          ok = html.includes(`<${value}`) || html.includes(`<${value} `);
          detail = ok ? `Tag <${value}> found` : `Tag <${value}> NOT found`;
        }
        break;
      }
      case "attr": {
        // Format: attr:data-theme=dark
        const eqIdx = value.indexOf("=");
        if (eqIdx === -1) {
          ok = html.includes(value);
          detail = ok ? `Attribute '${value}' found` : `Attribute '${value}' NOT found`;
        } else {
          const attrName = value.slice(0, eqIdx);
          const attrVal = value.slice(eqIdx + 1);
          ok = html.includes(`${attrName}="${attrVal}"`) || html.includes(`${attrName}='${attrVal}'`);
          detail = ok ? `Attribute ${attrName}="${attrVal}" found` : `Attribute ${attrName}="${attrVal}" NOT found`;
        }
        break;
      }
      default:
        detail = `Unknown assertion type '${type}' — skipped`;
        ok = true; // Don't penalize unknown types
    }

    results.push(`  ${ok ? "✅ PASS" : "❌ FAIL"} [${assertion}] — ${detail}`);
    if (ok) passed++; else failed++;
  }

  const summary = `DOM Verification (${url}): ${passed} passed, ${failed} failed`;
  const status = failed === 0 ? "✅ ALL ASSERTIONS PASSED" : `❌ ${failed} ASSERTION(S) FAILED`;
  return [status, summary, "", ...results].join("\n");
}

// ============================================================
// Git State Checkpointing
// ============================================================

// In-memory checkpoint store (session-scoped)
export const checkpointStore = [];

/**
 * rewind_to_checkpoint — restore workspace files and message context to a prior step.
 * The actual messages array rewind happens in agent.js which owns the messages array.
 * This tool restores the git working tree via git read-tree.
 */
async function rewindCheckpointTool({ step }) {
  if (checkpointStore.length === 0) {
    return "❌ No checkpoints available. Checkpoints are created automatically before each file-mutating step.";
  }

  // Find the requested step or fall back to most recent
  let checkpoint = checkpointStore.find(c => c.step === step);
  if (!checkpoint) {
    checkpoint = checkpointStore[checkpointStore.length - 1];
    console.log(chalk.yellow(`   ⚠ Step ${step} checkpoint not found. Using most recent: step ${checkpoint.step}`));
  }

  if (!checkpoint.stashHash) {
    return `❌ Checkpoint at step ${checkpoint.step} has no git stash hash (workspace may not be a git repo).`;
  }

  const workdir = getWorkdir();
  try {
    await new Promise((res, rej) => {
      exec(`git read-tree --reset -u ${checkpoint.stashHash}`, { cwd: workdir }, (err, stdout, stderr) => {
        if (err) return rej(new Error(stderr || err.message));
        res();
      });
    });
    console.log(chalk.green.bold(`   ✅ Workspace rewound to step ${checkpoint.step} snapshot`));
    // Signal agent.js to also rewind messages (agent reads this)
    process.env._SWADES_REWIND_STEP = String(checkpoint.step);
    return `✅ Workspace files rewound to step ${checkpoint.step}. Context will also be rewound. Stash: ${checkpoint.stashHash.slice(0, 8)}`;
  } catch (err) {
    return `❌ Rewind failed: ${err.message}. You can manually run: git read-tree --reset -u ${checkpoint.stashHash}`;
  }
}

// ---- Registry ----

const TOOL_REGISTRY = {
  read_file: readFileTool,
  write_file: writeFileTool,
  patch_file: patchFileTool,
  list_dir: listDirTool,
  run_command: runCommandTool,
  grep_search: grepSearchTool,
  index_codebase: indexCodebaseTool,
  peek_terminal: peekTerminalTool,
  extend_deadline: extendDeadlineTool,
  // Dynamic capability tools (Modes-as-Tools)
  run_simulation: runSimulationTool,
  spawn_subagents: spawnSubagentsTool,
  delegate_to_director: delegateToDirectorTool,
  // Text-only DOM verifier
  verify_dom_state: verifyDomStateTool,
  // Git state rewind
  rewind_to_checkpoint: rewindCheckpointTool,
};

/**
 * Execute a tool by name with parsed arguments.
 * Returns the tool output as a string.
 */
export async function executeTool(name, argsJson) {
  const fn = TOOL_REGISTRY[name];
  if (!fn) return `Unknown tool: ${name}`;

  try {
    const args = typeof argsJson === "string" ? JSON.parse(argsJson) : argsJson;
    return await fn(args);
  } catch (err) {
    return `Tool error (${name}): ${err.message}`;
  }
}
