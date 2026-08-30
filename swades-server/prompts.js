export const SYSTEM_PROMPT = `You are Swades Agent, an autonomous AI coding agent running server-side on a self-hosted phone server. A user has submitted a coding task against a GitHub repository that has been cloned into your workspace.

Your job is to:
1. Understand the codebase by reading files and searching for patterns
2. Plan your changes carefully
3. Make surgical, precise edits using patch_file (preferred) or write_file (for new files only)
4. Run tests and verify your changes compile/work
5. Complete the task fully — the user may not be watching

Rules:
- Use patch_file for ALL modifications to existing files. Never rewrite entire files.
- After writing or patching any file, review the syntax validation output and fix any issues immediately.
- Run relevant test commands (npm test, pytest, cargo test, go test) after making changes.
- If you're unsure about the project structure, use index_codebase and list_dir first.
- All file paths are relative to your workspace root.
- You CANNOT access files outside your workspace.
- Do NOT run dangerous commands (rm -rf /, sudo, kill, etc.).
- Be thorough. The user expects a complete, working solution.`;

export const TOOL_SCHEMAS = [
  {
    type: 'function',
    function: {
      name: 'read_file',
      description: 'Read a file from the workspace',
      parameters: {
        type: 'object',
        properties: {
          path: { type: 'string' },
          start_line: { type: 'number' },
          end_line: { type: 'number' }
        },
        required: ['path']
      }
    }
  },
  {
    type: 'function',
    function: {
      name: 'write_file',
      description: 'Write a new file to the workspace',
      parameters: {
        type: 'object',
        properties: {
          path: { type: 'string' },
          content: { type: 'string' }
        },
        required: ['path', 'content']
      }
    }
  },
  {
    type: 'function',
    function: {
      name: 'patch_file',
      description: 'Patch an existing file by replacing a specific string',
      parameters: {
        type: 'object',
        properties: {
          path: { type: 'string' },
          target: { type: 'string' },
          replacement: { type: 'string' }
        },
        required: ['path', 'target', 'replacement']
      }
    }
  },
  {
    type: 'function',
    function: {
      name: 'list_dir',
      description: 'List contents of a directory',
      parameters: {
        type: 'object',
        properties: {
          path: { type: 'string' },
          recursive: { type: 'boolean' }
        },
        required: ['path']
      }
    }
  },
  {
    type: 'function',
    function: {
      name: 'run_command',
      description: 'Run a shell command in the workspace',
      parameters: {
        type: 'object',
        properties: {
          command: { type: 'string' },
          cwd: { type: 'string' }
        },
        required: ['command']
      }
    }
  },
  {
    type: 'function',
    function: {
      name: 'grep_search',
      description: 'Search for a pattern across files',
      parameters: {
        type: 'object',
        properties: {
          pattern: { type: 'string' },
          path: { type: 'string' },
          include: { type: 'string' }
        },
        required: ['pattern']
      }
    }
  },
  {
    type: 'function',
    function: {
      name: 'index_codebase',
      description: 'Generate an index of the entire codebase',
      parameters: {
        type: 'object',
        properties: {},
        required: []
      }
    }
  },
  {
    type: 'function',
    function: {
      name: 'peek_terminal',
      description: 'Peek at the agent terminal log',
      parameters: {
        type: 'object',
        properties: {
          action: { type: 'string' }
        },
        required: []
      }
    }
  }
];
