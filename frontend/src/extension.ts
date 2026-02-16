import * as vscode from 'vscode';
import axios from 'axios';

export function activate(context: vscode.ExtensionContext) {

    console.log('AI Reviewer is active!');

    // Create a collection to hold the colored squiggly lines
    const diagnosticCollection = vscode.languages.createDiagnosticCollection('ai-reviewer');
    context.subscriptions.push(diagnosticCollection);

    let disposable = vscode.commands.registerCommand('ai-reviewer-extension.reviewCode', async () => {

        const editor = vscode.window.activeTextEditor;
        if (!editor) {
            vscode.window.showErrorMessage('No active editor!');
            return;
        }

        const document = editor.document;
        const code = document.getText();
        
        // Clear old markers before starting new review
        diagnosticCollection.clear();

        const payload = {
            code_content: code,
            language: document.languageId, 
            file_name: "test.py" // Ideally, pass document.fileName
        };

        try {
            vscode.window.setStatusBarMessage('AI: Reviewing...', 3000);
            
            // Call the Backend
            const response = await axios.post('http://127.0.0.1:8001/review', payload);
            const issues = response.data.issues;
            
            if (!issues || issues.length === 0) {
                vscode.window.showInformationMessage('No issues found! Clean code.');
                return;
            }

            const diagnostics: vscode.Diagnostic[] = [];

            for (const issue of issues) {
                const lineIndex = (issue.line || 1) - 1; 
                const range = new vscode.Range(lineIndex, 0, lineIndex, 100);

                // --- DYNAMIC SEVERITY LOGIC ---
                // Distinguishes between critical bugs and AI suggestions
                let severity: vscode.DiagnosticSeverity;

                if (issue.tool === "pylint" || issue.type.includes("Security")) {
                    severity = vscode.DiagnosticSeverity.Error; // Red line
                } else if (issue.tool === "AST Parser") {
                    severity = vscode.DiagnosticSeverity.Warning; // Orange/Yellow line
                } else {
                    // This covers AI-Reviewer (CodeT5) suggestions
                    severity = vscode.DiagnosticSeverity.Information; // Blue line
                }

                const diagnostic = new vscode.Diagnostic(
                    range, 
                    `[${issue.tool}] ${issue.msg}`, 
                    severity
                );
                
                diagnostics.push(diagnostic);
            }

            // Apply the diagnostics to the file
            diagnosticCollection.set(document.uri, diagnostics);
            vscode.window.showWarningMessage(`Found ${issues.length} issues across 4 analysis layers!`);

        } catch (error) {
            console.error(error);
            // This error occurs if the backend is not running or still loading models
            vscode.window.showErrorMessage('Error connecting to backend. Ensure python app.py is running.');
        }
    });

    context.subscriptions.push(disposable);
}

export function deactivate() {}