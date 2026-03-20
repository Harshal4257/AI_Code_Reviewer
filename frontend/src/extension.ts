import * as vscode from 'vscode';
import axios from 'axios';

export function activate(context: vscode.ExtensionContext) {
    const diagnosticCollection = vscode.languages.createDiagnosticCollection('ai-reviewer');
    context.subscriptions.push(diagnosticCollection);

    // 1. Register Quick Fix Provider for Python
    context.subscriptions.push(
        vscode.languages.registerCodeActionsProvider('python', new AIQuickFixProvider(), {
            providedCodeActionKinds: [vscode.CodeActionKind.QuickFix]
        })
    );

    // 2. Main Review Command
    let reviewDisposable = vscode.commands.registerCommand('ai-reviewer-extension.reviewCode', async () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) return;

        const document = editor.document;
        diagnosticCollection.clear();

        try {
            vscode.window.setStatusBarMessage('AI: Reviewing (Loading models may take time)...', 10000);

            const response = await axios.post('http://127.0.0.1:8001/review', {
                code_content: document.getText(),
                language: document.languageId,
                file_name: document.fileName
            }, {
                timeout: 180000 
            });

            const diagnostics: vscode.Diagnostic[] = [];
            
            // Get total lines to prevent "Illegal value" crashes
            const totalLines = document.lineCount;

            for (const issue of response.data.issues) {
                // --- LINE SAFETY GUARD ---
                // 1. Ensure line is at least 1 (backend sometimes sends 0)
                // 2. Convert to 0-based index
                // 3. Clamp between 0 and (totalLines - 1)
                let rawLine = issue.line || 1;
                let lineIndex = Math.max(0, Math.min(rawLine - 1, totalLines - 1));
                
                try {
                    const line = document.lineAt(lineIndex);
                    const range = line.range; 

                    let severity = vscode.DiagnosticSeverity.Information;
                    if (issue.tool === "CodeBERT" || issue.type.includes("Security")) {
                        severity = vscode.DiagnosticSeverity.Error;
                    } else if (issue.tool === "AST Parser") {
                        severity = vscode.DiagnosticSeverity.Warning;
                    }

                    const diagnostic = new vscode.Diagnostic(range, `[${issue.tool}] ${issue.msg}`, severity);
                    
                    if (issue.tool === "AI-Reviewer") {
                        diagnostic.code = "AI_FIX"; 
                    }
                    
                    diagnostics.push(diagnostic);
                } catch (lineErr) {
                    console.error(`Could not create diagnostic for line ${lineIndex}:`, lineErr);
                }
            }
            diagnosticCollection.set(document.uri, diagnostics);
            vscode.window.setStatusBarMessage('AI: Review Complete!', 3000);

        } catch (error: any) {
            let errorMsg = 'Backend connection failed. Check if app.py is running.';
            if (error.code === 'ECONNABORTED') {
                errorMsg = 'AI Review timed out. The models are still loading on the server.';
            } else if (error.response) {
                errorMsg = `Server Error: ${error.response.status} - ${error.response.data.detail || 'Check backend logs.'}`;
            }
            
            vscode.window.showErrorMessage(errorMsg);
            console.error("Extension Request Error:", error);
        }
    });

    // 3. Command to Apply All AI Suggestions at once
    let applyAllDisposable = vscode.commands.registerCommand('ai-reviewer-extension.applyAllFixes', async () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) return;

        const document = editor.document;
        const diagnostics = diagnosticCollection.get(document.uri);
        
        if (!diagnostics) return;

        const edit = new vscode.WorkspaceEdit();
        let count = 0;

        for (const diag of diagnostics) {
            const isAiFix = typeof diag.code === 'object' ? diag.code.value === "AI_FIX" : diag.code === "AI_FIX";
            if (isAiFix && diag.message.includes("refactoring to:")) {
                const suggestion = diag.message.split("refactoring to: ")[1];
                if (suggestion) {
                    edit.replace(document.uri, diag.range, suggestion.trim());
                    count++;
                }
            }
        }

        if (count > 0) {
            await vscode.workspace.applyEdit(edit);
            vscode.window.showInformationMessage(`Applied ${count} AI refactoring suggestions.`);
        }
    });

    context.subscriptions.push(reviewDisposable, applyAllDisposable);
}

// 4. Quick Fix Provider Class
class AIQuickFixProvider implements vscode.CodeActionProvider {
    public provideCodeActions(document: vscode.TextDocument, range: vscode.Range, context: vscode.CodeActionContext): vscode.CodeAction[] {
        return context.diagnostics
            .filter(diag => {
                const code = typeof diag.code === 'object' ? diag.code.value : diag.code;
                return code === "AI_FIX" && diag.message.includes("refactoring to:");
            })
            .map(diag => this.createFix(document, diag));
    }

    private createFix(document: vscode.TextDocument, diagnostic: vscode.Diagnostic): vscode.CodeAction {
        const fix = new vscode.CodeAction(`✨ Apply AI Suggestion`, vscode.CodeActionKind.QuickFix);
        const edit = new vscode.WorkspaceEdit();
        
        const suggestion = diagnostic.message.split("refactoring to: ")[1];
        if (suggestion) {
            edit.replace(document.uri, diagnostic.range, suggestion.trim());
            fix.edit = edit;
            fix.diagnostics = [diagnostic];
            fix.isPreferred = true;
        }

        return fix;
    }
}