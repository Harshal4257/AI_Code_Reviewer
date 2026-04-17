import * as vscode from 'vscode';
import axios from 'axios';
import * as path from 'path';
import * as cp from 'child_process';

let diagnosticCollection: vscode.DiagnosticCollection;

const DEFAULT_API_URL = 'https://ai-code-reviewer-f1mo.onrender.com';

// --- Track AI-fixed files for PR Simulation ---
const fixedFiles = new Set<string>();
let lastFixedFileName = "";
let lastIssuesSummary = "";

function getApiUrl(): string {
    const config = vscode.workspace.getConfiguration('aiReviewer');
    let url = config.get<string>('backendUrl') || DEFAULT_API_URL;
    return url.trim().replace(/\/+$/, '');
}

export function activate(context: vscode.ExtensionContext) {
    diagnosticCollection = vscode.languages.createDiagnosticCollection('ai-reviewer');
    context.subscriptions.push(diagnosticCollection);

    context.subscriptions.push(
        vscode.languages.registerCodeActionsProvider('python', new AIQuickFixProvider(), {
            providedCodeActionKinds: [vscode.CodeActionKind.QuickFix]
        })
    );

    // ─── REVIEW CODE ───────────────────────────────────────────────────────────
    let reviewDisposable = vscode.commands.registerCommand('ai-reviewer-extension.reviewCode', async () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) { return; }

        const document = editor.document;
        const apiUrl = getApiUrl();
        diagnosticCollection.clear();

        try {
            vscode.window.setStatusBarMessage('$(sync~spin) AI: Reviewing code...', 60000);

            const response = await axios.post(`${apiUrl}/review`, {
                code_content: document.getText(),
                language: document.languageId,
                file_name: document.fileName
            }, { timeout: 180000 });

            const allIssues: any[] = response.data.issues;
            const hasFullFix = allIssues.some(i =>
                i.tool === 'AI-Reviewer' && i.msg.includes('FULL_FILE_FIX_AVAILABLE')
            );
            const displayIssues = allIssues.filter(i =>
                !i.msg.includes('FULL_FILE_FIX_AVAILABLE')
            );

            lastIssuesSummary = displayIssues
                .map(i => `${i.category}: ${i.msg}`)
                .join('; ')
                .substring(0, 300);

            const diagnostics: vscode.Diagnostic[] = [];
            let securityCount = 0;
            let errorCount = 0;
            let warningCount = 0;

            for (const issue of displayIssues) {
                const rawLine: number = issue.line || 1;
                const lineIndex = Math.max(0, Math.min(rawLine - 1, document.lineCount - 1));

                try {
                    const lineObj = document.lineAt(lineIndex);
                    const category: string = issue.category || 'warning';
                    let severity: vscode.DiagnosticSeverity;

                    if (category === 'security') {
                        severity = vscode.DiagnosticSeverity.Error;
                        securityCount++;
                    } else if (category === 'error') {
                        severity = vscode.DiagnosticSeverity.Warning;
                        errorCount++;
                    } else {
                        severity = vscode.DiagnosticSeverity.Information;
                        warningCount++;
                    }

                    const diag = new vscode.Diagnostic(lineObj.range, `[${issue.tool}] ${issue.msg}`, severity);
                    if (issue.tool === 'AI-Reviewer') { diag.code = 'AI_FIX'; }
                    diagnostics.push(diag);
                } catch (err) {
                    console.error(`Diagnostic error:`, err);
                }
            }

            if (hasFullFix && displayIssues.length > 0) {
                const fixAllDiag = new vscode.Diagnostic(
                    document.lineAt(0).range,
                    `[AI-Reviewer] Complete fix available — ${securityCount} 🔴, ${errorCount} 🟡, ${warningCount} 🔵`,
                    vscode.DiagnosticSeverity.Hint
                );
                fixAllDiag.code = 'AI_FIX_ALL';
                diagnostics.push(fixAllDiag);
            }

            diagnosticCollection.set(document.uri, diagnostics);

            if (displayIssues.length === 0) {
                vscode.window.showInformationMessage('✅ AI Review Complete: No issues found!');
            } else {
                vscode.window.showWarningMessage(`AI Review: Found ${displayIssues.length} issues. Click Quick Fix to apply.`);
            }

        } catch (error: any) {
            handleError(error, apiUrl);
        } finally {
            vscode.window.setStatusBarMessage('');
        }
    });

    // ─── APPLY ALL FIXES ───────────────────────────────────────────────────────
    let applyAllDisposable = vscode.commands.registerCommand('ai-reviewer-extension.applyAllFixes', async () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) { return; }
        const apiUrl = getApiUrl();

        try {
            vscode.window.setStatusBarMessage('$(sync~spin) AI: Applying fixes...', 15000);
            const response = await axios.get(`${apiUrl}/fix`, { timeout: 30000 });

            if (!response.data.available || !response.data.fixed_code) {
                vscode.window.showWarningMessage('No AI fix available. Run Review Code first.');
                return;
            }

            const document = editor.document;
            const fullRange = new vscode.Range(0, 0, document.lineCount, 0);
            const edit = new vscode.WorkspaceEdit();
            edit.replace(document.uri, fullRange, response.data.fixed_code);
            await vscode.workspace.applyEdit(edit);
            await document.save();

            diagnosticCollection.set(document.uri, []);

            fixedFiles.add(document.fileName);
            lastFixedFileName = path.basename(document.fileName);

            const selection = await vscode.window.showInformationMessage(
                `✅ All fixes applied to ${lastFixedFileName}! Push to GitHub?`,
                'Push to GitHub',
                'Later'
            );

            if (selection === 'Push to GitHub') {
                vscode.commands.executeCommand('ai-reviewer-extension.pushToGitHub');
            }

        } catch (error: any) {
            handleError(error, apiUrl);
        } finally {
            vscode.window.setStatusBarMessage('');
        }
    });

    // ─── PUSH TO GITHUB (PR SIMULATION) — ALL 8 EDGE CASES ───────────────────
    let pushDisposable = vscode.commands.registerCommand('ai-reviewer-extension.pushToGitHub', async () => {

        // ── EDGE CASE 1: No AI-fixed files tracked ─────────────────────────────
        if (fixedFiles.size === 0) {
            vscode.window.showWarningMessage(
                '⚠️ No AI-fixed files to push. Run "Review Code" then "Apply AI Fix" first.'
            );
            return;
        }

        // ── EDGE CASE 2: No workspace folder open ──────────────────────────────
        // Fallback: use the directory of the currently open file
        let workspaceFolder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;

        if (!workspaceFolder) {
            const activeFile = vscode.window.activeTextEditor?.document.uri.fsPath;
            if (activeFile) {
                workspaceFolder = path.dirname(activeFile);
                vscode.window.showInformationMessage(
                    `ℹ️ No folder open in VS Code. Using file's directory: ${workspaceFolder}`
                );
            } else {
                vscode.window.showErrorMessage(
                    '❌ No workspace folder or open file found. Open your project folder in VS Code first.'
                );
                return;
            }
        }

        // ── EDGE CASE 3: Git not installed ─────────────────────────────────────
        const gitInstalled = await runCommand('git --version', workspaceFolder);
        if (gitInstalled.error) {
            const choice = await vscode.window.showErrorMessage(
                '❌ Git is not installed or not in PATH.',
                'Download Git'
            );
            if (choice === 'Download Git') {
                vscode.env.openExternal(vscode.Uri.parse('https://git-scm.com/downloads'));
            }
            return;
        }

        // ── EDGE CASE 4: Git not initialized in this folder ────────────────────
        const isRepo = await runCommand('git rev-parse --is-inside-work-tree', workspaceFolder);
        if (isRepo.error) {
            const choice = await vscode.window.showErrorMessage(
                '❌ This folder is not a Git repository.',
                'Initialize Git Repo',
                'Cancel'
            );
            if (choice === 'Initialize Git Repo') {
                const initResult = await runCommand('git init', workspaceFolder);
                if (initResult.error) {
                    vscode.window.showErrorMessage('❌ Failed to initialize Git repository.');
                    return;
                }
                vscode.window.showInformationMessage(
                    '✅ Git repository initialized. Please connect it to GitHub and try pushing again.'
                );
            }
            // Either way — stop here. User needs to connect remote first.
            return;
        }

        // ── EDGE CASE 5: No remote configured ──────────────────────────────────
        const remoteCheck = await runCommand('git remote', workspaceFolder);
        const hasRemote = !remoteCheck.error && remoteCheck.stdout.trim().length > 0;

        if (!hasRemote) {
            const repoUrl = await vscode.window.showInputBox({
                prompt: '🔗 No GitHub remote found. Enter your GitHub repository URL to connect:',
                placeHolder: 'https://github.com/yourusername/your-repo.git',
                ignoreFocusOut: true,
                validateInput: (val) => {
                    if (!val.trim()) { return 'URL cannot be empty'; }
                    if (!val.startsWith('https://') && !val.startsWith('git@')) {
                        return 'Must be a valid GitHub URL (https:// or git@github.com)';
                    }
                    return null;
                }
            });

            if (!repoUrl) { return; } // user cancelled

            const addRemote = await runCommand(
                `git remote add origin "${repoUrl.trim()}"`,
                workspaceFolder
            );
            if (addRemote.error) {
                vscode.window.showErrorMessage(
                    `❌ Failed to add remote: ${addRemote.stdout || 'Unknown error'}`
                );
                return;
            }
            vscode.window.showInformationMessage('✅ GitHub remote linked successfully!');
        }

        // ── EDGE CASE 6: Multiple branches — let user pick ─────────────────────
        const branchResult = await runCommand(
            'git branch --format=%(refname:short)',
            workspaceFolder
        );

        // Get current branch regardless
        const currentBranchResult = await runCommand(
            'git rev-parse --abbrev-ref HEAD',
            workspaceFolder
        );
        const currentBranch = currentBranchResult.stdout.trim() || 'main';

        let targetBranch = currentBranch;

        if (!branchResult.error) {
            const branches = branchResult.stdout
                .split('\n')
                .map(b => b.trim())
                .filter(b => b.length > 0);

            if (branches.length > 1) {
                // Mark current branch clearly in the list
                const branchItems = branches.map(b =>
                    b === currentBranch ? `${b} (current)` : b
                );

                const picked = await vscode.window.showQuickPick(branchItems, {
                    placeHolder: `Select branch to push to (currently on: ${currentBranch})`,
                    ignoreFocusOut: true
                });

                if (!picked) { return; } // user cancelled

                // Strip the " (current)" label if present
                targetBranch = picked.replace(' (current)', '').trim();

                // If user picked a different branch, check it out
                if (targetBranch !== currentBranch) {
                    const checkoutResult = await runCommand(
                        `git checkout "${targetBranch}"`,
                        workspaceFolder
                    );
                    if (checkoutResult.error) {
                        vscode.window.showErrorMessage(
                            `❌ Failed to switch to branch "${targetBranch}". Check for uncommitted changes.`
                        );
                        return;
                    }
                }
            }
        }

        // ── EDGE CASE 7: Nothing to commit (no actual changes detected) ────────
        const statusResult = await runCommand('git status --porcelain', workspaceFolder);
        if (!statusResult.error && statusResult.stdout.trim().length === 0) {
            vscode.window.showInformationMessage(
                'ℹ️ No changes detected in your files. Nothing to commit or push.'
            );
            fixedFiles.clear();
            lastIssuesSummary = '';
            lastFixedFileName = '';
            return;
        }

        // ── GET AI COMMIT MESSAGE ───────────────────────────────────────────────
        const apiUrl = getApiUrl();
        const fixedFilesList = Array.from(fixedFiles);
        const fileNames = fixedFilesList.map(f => path.basename(f));

        vscode.window.setStatusBarMessage('$(sync~spin) AI: Generating commit message...', 15000);

        let suggestedMessage = `fix: applied AI code review fixes to ${fileNames.join(', ')}`;

        try {
            const commitRes = await axios.post(`${apiUrl}/suggest-commit`, {
                fixedFiles: fileNames,
                issuesSummary: lastIssuesSummary
            }, { timeout: 30000 });

            if (commitRes.data.commitMessage) {
                suggestedMessage = commitRes.data.commitMessage;
            }
        } catch {
            // Silent fallback — default message is already set above
        } finally {
            vscode.window.setStatusBarMessage('');
        }

        // ── EDITABLE COMMIT MESSAGE INPUT ──────────────────────────────────────
        const commitMessage = await vscode.window.showInputBox({
            prompt: '✏️ Edit your commit message (AI-generated). Press Enter to push.',
            value: suggestedMessage,
            placeHolder: 'fix: your commit message here',
            ignoreFocusOut: true,
            validateInput: (val) => val.trim().length === 0 ? 'Commit message cannot be empty' : null
        });

        if (!commitMessage) { return; } // user pressed Escape

        // ── BUILD AND RUN GIT COMMANDS ─────────────────────────────────────────
        const quotedFiles = fixedFilesList.map(f => `"${f}"`).join(' ');
        const safeMessage = commitMessage.replace(/"/g, '\\"');

        // ── EDGE CASE 8: First push / no upstream — detect and handle ──────────
        // Check if this branch has an upstream tracking branch set
        const upstreamCheck = await runCommand(
            `git rev-parse --abbrev-ref "${targetBranch}@{upstream}"`,
            workspaceFolder
        );
        const needsUpstream = upstreamCheck.error; // true = no upstream set yet

        const pushCommand = needsUpstream
            ? `git push --set-upstream origin "${targetBranch}"`
            : `git push`;

        // Open terminal and run all commands visibly
        const terminal = vscode.window.createTerminal({
            name: '🤖 AI Reviewer — GitHub Push',
            cwd: workspaceFolder
        });
        terminal.show(true);

        terminal.sendText(`git add ${quotedFiles}`);
        terminal.sendText(`git commit -m "${safeMessage}"`);
        terminal.sendText(pushCommand);

        // Clear state after push initiated
        fixedFiles.clear();
        lastIssuesSummary = '';
        lastFixedFileName = '';

        vscode.window.showInformationMessage(
            `🚀 Pushing to branch "${targetBranch}" — "${commitMessage}"`,
            'View Terminal'
        ).then(sel => {
            if (sel === 'View Terminal') { terminal.show(); }
        });
    });

    context.subscriptions.push(reviewDisposable, applyAllDisposable, pushDisposable);
}

// ─── HELPER: Run shell command ────────────────────────────────────────────────
function runCommand(command: string, cwd: string): Promise<{ stdout: string; error: boolean }> {
    return new Promise((resolve) => {
        cp.exec(command, { cwd }, (err, stdout, stderr) => {
            resolve({
                stdout: (stdout || stderr || '').trim(),
                error: !!err
            });
        });
    });
}

function handleError(error: any, url: string) {
    let msg = `Connection failed. Is backend running at ${url}?`;
    if (error.response?.status === 404) {
        msg = `404 Not Found: The backend doesn't recognize this path. Check your API URL.`;
    } else if (error.code === 'ECONNABORTED') {
        msg = 'Timed out — Render might be cold starting. Try again in 30s.';
    }
    vscode.window.showErrorMessage(msg);
}

// ─── QUICK FIX PROVIDER ───────────────────────────────────────────────────────
class AIQuickFixProvider implements vscode.CodeActionProvider {
    public provideCodeActions(
        document: vscode.TextDocument,
        range: vscode.Range,
        context: vscode.CodeActionContext
    ): vscode.CodeAction[] {
        return context.diagnostics.map(diag => {
            const code = typeof diag.code === 'object' ? diag.code.value : diag.code;
            if (code === 'AI_FIX_ALL') {
                const action = new vscode.CodeAction(
                    '✨ Apply AI Fix (Full File)',
                    vscode.CodeActionKind.QuickFix
                );
                action.command = {
                    command: 'ai-reviewer-extension.applyAllFixes',
                    title: 'Apply'
                };
                return action;
            }
            return null;
        }).filter(a => a !== null) as vscode.CodeAction[];
    }
}