import * as vscode from 'vscode';
import axios from 'axios';

export function activate(context: vscode.ExtensionContext) {
    const diagnosticCollection = vscode.languages.createDiagnosticCollection('ai-reviewer');
    context.subscriptions.push(diagnosticCollection);

    // 1. Register the Quick Fix Provider specifically for Python files
    context.subscriptions.push(
        vscode.languages.registerCodeActionsProvider('python', new AIQuickFixProvider(), {
            providedCodeActionKinds: [vscode.CodeActionKind.QuickFix]
        })
    );

    let disposable = vscode.commands.registerCommand('ai-reviewer-extension.reviewCode', async () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) return;

        const document = editor.document;
        diagnosticCollection.clear();

        try {
            vscode.window.setStatusBarMessage('AI: Reviewing...', 3000);
            const response = await axios.post('http://127.0.0.1:8001/review', {
                code_content: document.getText(),
                language: document.languageId,
                file_name: "test.py"
            });

            const diagnostics: vscode.Diagnostic[] = [];
            for (const issue of response.data.issues) {
                const lineIndex = (issue.line || 1) - 1;
                const range = new vscode.Range(lineIndex, 0, lineIndex, 100);

                let severity = vscode.DiagnosticSeverity.Information;
                if (issue.tool === "pylint" || issue.type.includes("Security")) {
                    severity = vscode.DiagnosticSeverity.Error;
                } else if (issue.tool === "AST Parser") {
                    severity = vscode.DiagnosticSeverity.Warning;
                }

                // Create the diagnostic with the combined tool and message string
                const diagnostic = new vscode.Diagnostic(range, `[${issue.tool}] ${issue.msg}`, severity);
                
                // Store the raw message in the diagnostic code field for easy filtering in the provider
                if (issue.tool === "AI-Reviewer") {
                    diagnostic.code = "AI_FIX"; 
                }
                
                diagnostics.push(diagnostic);
            }
            diagnosticCollection.set(document.uri, diagnostics);
        } catch (error) {
            vscode.window.showErrorMessage('Backend connection failed. Ensure app.py is running.');
        }
    });
    context.subscriptions.push(disposable);
}

// 2. The Refined Quick Fix Class
// --- Updated Quick Fix Class ---
class AIQuickFixProvider implements vscode.CodeActionProvider {
    public provideCodeActions(
        document: vscode.TextDocument, 
        range: vscode.Range | vscode.Selection, 
        context: vscode.CodeActionContext
    ): vscode.CodeAction[] {
        // Find all diagnostics that were tagged with "AI_FIX"
        return context.diagnostics
            .filter(diag => {
                // Check if the diagnostic code is AI_FIX (handles both string and object forms)
                const isAiFix = typeof diag.code === 'object' ? diag.code.value === "AI_FIX" : diag.code === "AI_FIX";
                return isAiFix && diag.message.includes("refactoring to:");
            })
            .map(diag => this.createFix(document, diag));
    }

    private createFix(document: vscode.TextDocument, diagnostic: vscode.Diagnostic): vscode.CodeAction {
        const fix = new vscode.CodeAction(`✨ Apply AI Suggestion`, vscode.CodeActionKind.QuickFix);
        const edit = new vscode.WorkspaceEdit();
        
        // Use a more robust regex to extract the code after the colon
        const message = diagnostic.message;
        const suggestionMatch = message.match(/refactoring to:\s+(.*)/);
        const suggestedCode = suggestionMatch ? suggestionMatch[1].trim() : "";
        
        if (suggestedCode) {
            // Replace the line with the AI's suggested code
            edit.replace(document.uri, diagnostic.range, suggestedCode);
            fix.edit = edit;
            fix.diagnostics = [diagnostic];
            fix.isPreferred = true; // Makes it the default choice for Ctrl + .
        }

        return fix;
    }
}