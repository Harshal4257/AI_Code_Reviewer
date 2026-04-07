import * as vscode from 'vscode';
import axios from 'axios';

let diagnosticCollection: vscode.DiagnosticCollection;

export function activate(context: vscode.ExtensionContext) {
    diagnosticCollection = vscode.languages.createDiagnosticCollection('ai-reviewer');
    context.subscriptions.push(diagnosticCollection);

    // 1. Register Quick Fix Provider
    context.subscriptions.push(
        vscode.languages.registerCodeActionsProvider('python', new AIQuickFixProvider(), {
            providedCodeActionKinds: [vscode.CodeActionKind.QuickFix]
        })
    );

    // 2. Main Review Command
    let reviewDisposable = vscode.commands.registerCommand('ai-reviewer-extension.reviewCode', async () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) { return; }

        const document = editor.document;
        diagnosticCollection.clear();

        try {
            vscode.window.setStatusBarMessage('$(sync~spin) AI: Reviewing code...', 60000);

            const response = await axios.post('http://127.0.0.1:8001/review', {
                code_content: document.getText(),
                language: document.languageId,
                file_name: document.fileName
            }, { timeout: 180000 });

            const allIssues: any[] = response.data.issues;

            // Separate the full-fix signal from display issues
            const hasFullFix = allIssues.some(i =>
                i.tool === 'AI-Reviewer' && i.msg.includes('FULL_FILE_FIX_AVAILABLE')
            );
            const displayIssues = allIssues.filter(i =>
                !i.msg.includes('FULL_FILE_FIX_AVAILABLE')
            );

            const diagnostics: vscode.Diagnostic[] = [];
            const totalLines = document.lineCount;

            // Category counts for status bar summary
            let securityCount = 0;
            let errorCount = 0;
            let warningCount = 0;

            for (const issue of displayIssues) {
                const rawLine: number = issue.line || 1;
                const lineIndex = Math.max(0, Math.min(rawLine - 1, totalLines - 1));

                try {
                    const lineObj = document.lineAt(lineIndex);
                    const category: string = issue.category || 'warning';

                    // ===================================================
                    // COLOR CODING BY CATEGORY:
                    // 🔴 Error   = Security vulnerabilities
                    // 🟡 Warning = Logic bugs, runtime errors, bad code
                    // 🔵 Info    = Code quality, style, suggestions
                    // ===================================================
                    let severity: vscode.DiagnosticSeverity;

                    if (category === 'security') {
                        severity = vscode.DiagnosticSeverity.Error;    // 🔴 Red
                        securityCount++;
                    } else if (category === 'error') {
                        severity = vscode.DiagnosticSeverity.Warning;  // 🟡 Yellow
                        errorCount++;
                    } else {
                        severity = vscode.DiagnosticSeverity.Information; // 🔵 Blue
                        warningCount++;
                    }

                    const diag = new vscode.Diagnostic(
                        lineObj.range,
                        `[${issue.tool}] ${issue.msg}`,
                        severity
                    );

                    // Tag for quick fix
                    if (issue.tool === 'AI-Reviewer') {
                        diag.code = 'AI_FIX';
                    }

                    diagnostics.push(diag);
                } catch (err) {
                    console.error(`Diagnostic error line ${lineIndex}:`, err);
                }
            }

            // Add "full file fix available" diagnostic at the top
            if (hasFullFix && displayIssues.length > 0) {
                const fixAllDiag = new vscode.Diagnostic(
                    document.lineAt(0).range,
                    `[AI-Reviewer] Complete fix available — ${securityCount} security 🔴, ${errorCount} errors 🟡, ${warningCount} warnings 🔵`,
                    vscode.DiagnosticSeverity.Hint
                );
                fixAllDiag.code = 'AI_FIX_ALL';
                diagnostics.push(fixAllDiag);
            }

            diagnosticCollection.set(document.uri, diagnostics);

            if (displayIssues.length === 0) {
                vscode.window.setStatusBarMessage('$(check) AI: Code is clean — no issues found!', 6000);
                vscode.window.showInformationMessage('✅ AI Review Complete: No issues found! Your code is clean.');
            } else {
                const summary = `🔴 ${securityCount} security  🟡 ${errorCount} errors  🔵 ${warningCount} warnings`;
                vscode.window.setStatusBarMessage(`$(warning) AI: ${displayIssues.length} issue(s) found`, 6000);
                vscode.window.showWarningMessage(
                    `AI Review: ${displayIssues.length} issue(s) — ${summary}. Click Quick Fix to apply all fixes.`
                );
            }

        } catch (error: any) {
            let msg = 'Backend connection failed. Is app.py running?';
            if (error.code === 'ECONNABORTED') {
                msg = 'Review timed out — models still loading. Try again.';
            } else if (error.response) {
                msg = `Server Error ${error.response.status}: ${error.response.data?.detail || 'See backend logs.'}`;
            }
            vscode.window.showErrorMessage(msg);
            console.error('Review error:', error);
        }
    });

    // 3. Apply All Fixes — replaces entire file with Groq-verified clean version
    let applyAllDisposable = vscode.commands.registerCommand('ai-reviewer-extension.applyAllFixes', async () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) { return; }

        try {
            vscode.window.setStatusBarMessage('$(sync~spin) AI: Applying fixes...', 15000);

            const response = await axios.get('http://127.0.0.1:8001/fix', { timeout: 30000 });

            if (!response.data.available || !response.data.fixed_code) {
                vscode.window.showWarningMessage('No AI fix available. Please run Review Code first.');
                return;
            }

            const fixedCode: string = response.data.fixed_code;
            const document = editor.document;

            const fullRange = new vscode.Range(
                new vscode.Position(0, 0),
                new vscode.Position(
                    document.lineCount - 1,
                    document.lineAt(document.lineCount - 1).text.length
                )
            );

            const edit = new vscode.WorkspaceEdit();
            edit.replace(document.uri, fullRange, fixedCode);
            await vscode.workspace.applyEdit(edit);

            // Clear all diagnostics — file is now clean
            diagnosticCollection.set(document.uri, []);

            vscode.window.setStatusBarMessage('$(check) AI: All fixes applied!', 6000);
            vscode.window.showInformationMessage(
                '✅ All fixes applied! Run Review Code again to confirm code is clean.'
            );

        } catch (error: any) {
            vscode.window.showErrorMessage('Failed to apply fixes. Is app.py running?');
            console.error('Apply fixes error:', error);
        }
    });

    // 4. Clear single line diagnostic after inline quick fix
    let clearLineDisposable = vscode.commands.registerCommand(
        'ai-reviewer-extension.clearLineDiagnostic',
        (uri: vscode.Uri, lineIndex: number) => {
            const current = diagnosticCollection.get(uri) || [];
            const remaining = current.filter(d => d.range.start.line !== lineIndex);
            diagnosticCollection.set(uri, remaining);
        }
    );

    context.subscriptions.push(reviewDisposable, applyAllDisposable, clearLineDisposable);
}

// 5. Quick Fix Provider
class AIQuickFixProvider implements vscode.CodeActionProvider {
    public provideCodeActions(
        document: vscode.TextDocument,
        range: vscode.Range,
        context: vscode.CodeActionContext
    ): vscode.CodeAction[] {
        const actions: vscode.CodeAction[] = [];

        for (const diag of context.diagnostics) {
            const code = typeof diag.code === 'object' ? diag.code.value : diag.code;

            // Full file fix
            if (code === 'AI_FIX_ALL') {
                const action = new vscode.CodeAction(
                    '✨ Apply AI Fix — fix entire file',
                    vscode.CodeActionKind.QuickFix
                );
                action.command = {
                    command: 'ai-reviewer-extension.applyAllFixes',
                    title: 'Apply full AI fix'
                };
                action.isPreferred = true;
                actions.push(action);
            }

            // Individual line fix
            if (code === 'AI_FIX' && diag.message.includes('refactoring to:')) {
                actions.push(this.createLineFix(document, diag));
            }
        }

        return actions;
    }

    private createLineFix(
        document: vscode.TextDocument,
        diagnostic: vscode.Diagnostic
    ): vscode.CodeAction {
        const fix = new vscode.CodeAction('✨ Apply AI Suggestion', vscode.CodeActionKind.QuickFix);
        const edit = new vscode.WorkspaceEdit();

        const suggestion = diagnostic.message.split('refactoring to: ')[1];
        if (suggestion) {
            const lineIndex = diagnostic.range.start.line;
            const lineObj = document.lineAt(lineIndex);
            const fullLineRange = new vscode.Range(
                new vscode.Position(lineIndex, 0),
                new vscode.Position(lineIndex, lineObj.text.length)
            );
            edit.replace(document.uri, fullLineRange, suggestion.trim());
            fix.edit = edit;
            fix.diagnostics = [diagnostic];
            fix.isPreferred = false;
            fix.command = {
                command: 'ai-reviewer-extension.clearLineDiagnostic',
                title: 'Clear after fix',
                arguments: [document.uri, lineIndex]
            };
        }

        return fix;
    }
}