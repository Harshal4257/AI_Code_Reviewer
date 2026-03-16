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
            vscode.window.setStatusBarMessage('AI: Reviewing...', 3000);
            const response = await axios.post('http://127.0.0.1:8001/review', {
                code_content: document.getText(),
                language: document.languageId,
                file_name: document.fileName
            });

            const diagnostics: vscode.Diagnostic[] = [];
            for (const issue of response.data.issues) {
                const lineIndex = (issue.line || 1) - 1;
                
                // --- PRECISE RANGE FIX ---
                // Get the actual line from the document to ensure we replace only that line
                const line = document.lineAt(lineIndex);
                const range = line.range; 

                let severity = vscode.DiagnosticSeverity.Information;
                if (issue.tool === "pylint" || issue.type.includes("Security")) {
                    severity = vscode.DiagnosticSeverity.Error;
                } else if (issue.tool === "AST Parser") {
                    severity = vscode.DiagnosticSeverity.Warning;
                }

                const diagnostic = new vscode.Diagnostic(range, `[${issue.tool}] ${issue.msg}`, severity);
                
                if (issue.tool === "AI-Reviewer") {
                    diagnostic.code = "AI_FIX"; 
                }
                
                diagnostics.push(diagnostic);
            }
            diagnosticCollection.set(document.uri, diagnostics);
        } catch (error) {
            vscode.window.showErrorMessage('Backend connection failed. Check if app.py is running.');
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
            // Using the diagnostic's own range ensures we only replace the target line
            edit.replace(document.uri, diagnostic.range, suggestion.trim());
            fix.edit = edit;
            fix.diagnostics = [diagnostic];
            fix.isPreferred = true;
        }

        return fix;
    }
}