import * as vscode from 'vscode';
import * as path from 'path';

export function activate(context) {
  console.log('Swades Agent terminal extension is active!');

  // Single command — zero choice paralysis.
  // Just asks for the task, mode is auto-detected by AI.
  context.subscriptions.push(
    vscode.commands.registerCommand('swades-agent.run', () => {
      runSwadesTerminal(context);
    })
  );

  // Power-user shortcuts (hidden from main command palette UX)
  context.subscriptions.push(
    vscode.commands.registerCommand('swades-agent.runAutonomous', () => {
      runSwadesTerminal(context, 'autonomous');
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('swades-agent.runCua', () => {
      runSwadesTerminal(context, 'cua');
    })
  );
}

export function deactivate() {}

async function runSwadesTerminal(context, forcedMode) {
  const workspaceFolders = vscode.workspace.workspaceFolders;
  if (!workspaceFolders || workspaceFolders.length === 0) {
    vscode.window.showErrorMessage('Please open a workspace folder before running Swades Agent.');
    return;
  }

  const workspacePath = workspaceFolders[0].uri.fsPath;
  const indexJsPath = path.join(context.extensionPath, 'src', 'index.js');

  // 1. Only ask for the task — that's it. Zero paralysis.
  const task = await vscode.window.showInputBox({
    prompt: "What do you need? (mode is auto-detected)",
    placeHolder: "e.g., Add email verification to auth.js and run tests",
    ignoreFocusOut: true,
    validateInput: (value) => {
      return value.trim() ? null : "Task cannot be empty.";
    }
  });

  if (!task) return;

  // 2. Build command — mode is either forced (power-user shortcut) or auto-detected by AI
  const escapedTask = task.replace(/"/g, '\\"');
  let cmd = `node "${indexJsPath}" "${escapedTask}"`;

  if (forcedMode === 'autonomous') {
    cmd += ' --autonomous';
  } else if (forcedMode === 'cua') {
    cmd += ' --cua';
  }
  // No flag = AI auto-detects the mode. No user decision needed.

  // 3. Retrieve or Create VS Code Terminal
  let terminal = vscode.window.terminals.find(t => t.name === "Swades Agent");
  if (!terminal) {
    terminal = vscode.window.createTerminal({
      name: "Swades Agent",
      cwd: workspacePath
    });
  }

  // Show the terminal and send execution command
  terminal.show(true);
  terminal.sendText(cmd);
}
