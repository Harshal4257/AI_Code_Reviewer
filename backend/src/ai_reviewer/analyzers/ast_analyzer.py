import ast
from typing import List, Dict, Any


class ASTAnalyzer:
    """
    AST-based structural code analyzer.
    Checks function length, argument count, and variable naming conventions.
    Analysis is delegated to the AI engine (Groq) for unified reporting.
    """

    def __init__(self):
        self.issues = []

    def analyze(self, code: str) -> List[Dict[str, Any]]:
        """
        Parses and analyzes the code structure using Python's AST module.
        Structural checks are performed and available but results are
        handled by the AI engine to maintain consistent line reporting.
        """
        self.issues = []
        try:
            tree = ast.parse(code)
            self._check_function_length(tree)
            self._check_argument_count(tree)
            self._check_variable_names(tree)
        except SyntaxError as e:
            # Syntax errors are reported by Groq with better context
            pass
        except Exception:
            pass

        # Results delegated to AI engine — return empty to avoid duplicates
        return []

    def _check_function_length(self, tree):
        """Rule: Functions should not be longer than 50 lines."""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                length = node.end_lineno - node.lineno
                if length > 50:
                    self.issues.append({
                        "tool": "AST Parser",
                        "type": "Design Issue",
                        "msg": f"Function '{node.name}' is too long ({length} lines). Consider breaking it down.",
                        "line": node.lineno
                    })

    def _check_argument_count(self, tree):
        """Rule: Functions should not have more than 5 arguments."""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                args_count = len(node.args.args)
                if args_count > 5:
                    self.issues.append({
                        "tool": "AST Parser",
                        "type": "Design Issue",
                        "msg": f"Function '{node.name}' has too many arguments ({args_count}). Limit is 5.",
                        "line": node.lineno
                    })

    def _check_variable_names(self, tree):
        """Rule: Variable names should be longer than 2 characters (except i, j, k)."""
        allowed_short_names = {'i', 'j', 'k', 'x', 'y', 'z', '_'}

        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                if len(node.id) < 3 and node.id not in allowed_short_names:
                    self.issues.append({
                        "tool": "AST Parser",
                        "type": "Naming Convention",
                        "msg": f"Variable name '{node.id}' is too short. Use descriptive names.",
                        "line": node.lineno
                    })