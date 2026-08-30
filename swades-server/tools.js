import fs from 'fs';
import path from 'path';
import { execSync } from 'child_process';

function validateSyntax(filePath, content) {
  const warnings = [];
  const ext = path.extname(filePath);
  
  if (['.js', '.mjs', '.cjs'].includes(ext)) {
    try {
      execSync(`node --check ${filePath}`, { stdio: 'pipe' });
    } catch (e) {
      warnings.push(`Node syntax error: ${e.stderr || e.stdout}`);
    }
  } else if (ext === '.py') {
    try {
      execSync(`python3 -m py_compile ${filePath}`, { stdio: 'pipe' });
    } catch (e) {
      warnings.push(`Python syntax error: ${e.stderr || e.stdout}`);
    }
  } else if (ext === '.json') {
    try {
      JSON.parse(content);
    } catch (e) {
      warnings.push(`JSON syntax error: ${e.message}`);
    }
  }
  
  // Balance check
  const stack = [];
  const pairs = { '}': '{', ']': '[', ')': '(' };
  for (let i = 0; i < content.length; i++) {
    const char = content[i];
    if (['{', '[', '('].includes(char)) {
      stack.push(char);
    } else if (['}', ']', ')'].includes(char)) {
      const top = stack.pop();
      if (top !== pairs[char]) {
        warnings.push(`Mismatched bracket: expected ${pairs[char]} but found ${char} at index ${i}`);
      }
    }
  }
  if (stack.length > 0) {
    warnings.push(`Unclosed brackets: ${stack.join(', ')}`);
  }
  
  return warnings;
}

export async function executeTool(context, name, args) {
  try {
    const { workdir } = context;
    
    if (name === 'read_file') {
      const { path: relPath, start_line, end_line } = args;
      const fullPath = path.resolve(workdir, relPath);
      if (!fullPath.startsWith(workdir)) throw new Error('Access denied outside workspace');
      if (!fs.existsSync(fullPath)) throw new Error('File not found');
      
      const content = fs.readFileSync(fullPath, 'utf8');
      const lines = content.split('\\n');
      const start = start_line ? Math.max(1, start_line) - 1 : 0;
      const end = end_line ? Math.min(lines.length, end_line) : lines.length;
      
      const resultLines = lines.slice(start, end).map((line, i) => `${start + i + 1} | ${line}`);
      let result = resultLines.join('\\n');
      if (result.length > 10000) result = result.slice(0, 10000) + '\\n... (truncated)';
      return result;
    }
    
    if (name === 'write_file') {
      const { path: relPath, content } = args;
      const fullPath = path.resolve(workdir, relPath);
      if (!fullPath.startsWith(workdir)) throw new Error('Access denied outside workspace');
      
      fs.mkdirSync(path.dirname(fullPath), { recursive: true });
      fs.writeFileSync(fullPath, content, 'utf8');
      
      const warnings = validateSyntax(fullPath, content);
      if (warnings.length > 0) {
        return `File written, but with syntax warnings:\\n${warnings.join('\\n')}`;
      }
      return 'File written successfully';
    }
    
    if (name === 'patch_file') {
      const { path: relPath, target, replacement } = args;
      const fullPath = path.resolve(workdir, relPath);
      if (!fullPath.startsWith(workdir)) throw new Error('Access denied outside workspace');
      if (!fs.existsSync(fullPath)) throw new Error('File not found');
      
      let content = fs.readFileSync(fullPath, 'utf8').replace(/\\r\\n/g, '\\n');
      const normTarget = target.replace(/\\r\\n/g, '\\n');
      
      const parts = content.split(normTarget);
      if (parts.length === 1) throw new Error('Target string not found in file (check indentation)');
      if (parts.length > 2) throw new Error('Target string found multiple times, add more context');
      
      content = parts.join(replacement.replace(/\\r\\n/g, '\\n'));
      fs.writeFileSync(fullPath, content, 'utf8');
      
      const warnings = validateSyntax(fullPath, content);
      if (warnings.length > 0) {
        return `File patched, but with syntax warnings:\\n${warnings.join('\\n')}`;
      }
      return 'File patched successfully';
    }
    
    if (name === 'list_dir') {
      const { path: relPath = '.', recursive } = args;
      const fullPath = path.resolve(workdir, relPath);
      if (!fullPath.startsWith(workdir)) throw new Error('Access denied outside workspace');
      
      const skip = ['.git', 'node_modules', '__pycache__', '.venv'];
      let output = [];
      
      function walk(dir, prefix = '') {
        if (output.length >= 200) return;
        if (!fs.existsSync(dir)) return;
        const items = fs.readdirSync(dir, { withFileTypes: true });
        for (const item of items) {
          if (skip.includes(item.name)) continue;
          if (output.length >= 200) {
             output.push(prefix + '... (truncated)');
             break;
          }
          if (item.isDirectory()) {
            output.push(`${prefix}${item.name}/`);
            if (recursive) walk(path.join(dir, item.name), prefix + '  ');
          } else {
            const stat = fs.statSync(path.join(dir, item.name));
            output.push(`${prefix}${item.name} (${stat.size} bytes)`);
          }
        }
      }
      walk(fullPath);
      return output.join('\\n');
    }
    
    if (name === 'run_command') {
      const { command, cwd = '.' } = args;
      const dangerous = ['rm -rf', 'sudo', 'kill', 'mkfs', 'dd if=', 'chmod 777', ':(){ ', 'format '];
      if (dangerous.some(d => command.includes(d))) {
        return `Error: Command contains dangerous pattern and was blocked.`;
      }
      
      const fullCwd = path.resolve(workdir, cwd);
      if (!fullCwd.startsWith(workdir)) throw new Error('Access denied outside workspace');
      
      try {
        const out = execSync(command, { cwd: fullCwd, timeout: 120000, maxBuffer: 1024 * 1024 }).toString();
        return out.length > 10000 ? out.slice(0, 10000) + '\\n... (truncated)' : out || 'Command completed with no output';
      } catch (e) {
        const errStr = (e.stderr ? e.stderr.toString() : '') + (e.stdout ? e.stdout.toString() : e.message);
        return `Error (code ${e.status || 1}):\\n${errStr}`;
      }
    }
    
    if (name === 'grep_search') {
      const { pattern, path: relPath = '.', include } = args;
      const fullPath = path.resolve(workdir, relPath);
      if (!fullPath.startsWith(workdir)) throw new Error('Access denied outside workspace');
      
      let cmd = `grep -rnI --color=never --exclude-dir=.git --exclude-dir=node_modules`;
      if (include) cmd += ` --include="${include}"`;
      cmd += ` -e "${pattern.replace(/"/g, '\\\\"')}" "${fullPath}"`;
      
      try {
        const out = execSync(cmd, { timeout: 60000 }).toString();
        return out.length > 10000 ? out.slice(0, 10000) + '\\n... (truncated)' : out || 'No matches found';
      } catch (e) {
        if (e.status === 1) return 'No matches found';
        return `Error: ${e.message}`;
      }
    }
    
    if (name === 'index_codebase') {
      return indexCodebase(context);
    }
    
    if (name === 'peek_terminal') {
      const logFile = path.join(path.dirname(workdir), 'agent.log');
      if (fs.existsSync(logFile)) {
        const content = fs.readFileSync(logFile, 'utf8').split('\\n').filter(Boolean);
        return content.slice(-50).join('\\n');
      }
      return 'No terminal log found';
    }
    
    throw new Error(`Unknown tool: ${name}`);
  } catch (err) {
    return `Tool Error: ${err.message}`;
  }
}

export function indexCodebase(context) {
  const { workdir } = context;
  const skip = ['.git', 'node_modules', '__pycache__', '.venv', 'dist', 'build'];
  let index = [];
  
  function walk(dir) {
    if (!fs.existsSync(dir)) return;
    const items = fs.readdirSync(dir, { withFileTypes: true });
    for (const item of items) {
      if (skip.includes(item.name)) continue;
      const fullPath = path.join(dir, item.name);
      if (item.isDirectory()) {
        walk(fullPath);
      } else {
        const stat = fs.statSync(fullPath);
        const relPath = path.relative(workdir, fullPath);
        let info = `${relPath} (${stat.size} bytes)`;
        const ext = path.extname(item.name);
        if (['.js', '.ts', '.py'].includes(ext) && stat.size < 50000) {
          const content = fs.readFileSync(fullPath, 'utf8');
          const classes = [...content.matchAll(/class\\s+([A-Za-z0-9_]+)/g)].map(m => m[1]);
          const funcs = [...content.matchAll(/function\\s+([A-Za-z0-9_]+)/g)].map(m => m[1]);
          const exports = [...content.matchAll(/export\\s+(?:const|let|var|function|class)\\s+([A-Za-z0-9_]+)/g)].map(m => m[1]);
          
          if (classes.length || funcs.length || exports.length) {
            info += ' [';
            if (classes.length) info += `Classes: ${classes.join(',')}; `;
            if (funcs.length) info += `Funcs: ${funcs.join(',')}; `;
            if (exports.length) info += `Exports: ${exports.join(',')}`;
            info += ']';
          }
        }
        index.push(info);
      }
    }
  }
  
  walk(workdir);
  return index.join('\\n') || 'Empty codebase';
}
