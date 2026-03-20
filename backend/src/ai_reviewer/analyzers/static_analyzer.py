import json
import ast
import sys
from io import StringIO
from typing import List, Dict, Any

# Tool Imports
from pylint.lint import Run
from pylint.reporters.json_reporter import JSONReporter
from bandit.core.manager import BanditManager
from bandit.core.config import BanditConfig
from radon.visitors import ComplexityVisitor

# Project Imports
from src.ai_reviewer.schemas.review_schema import Issue
from src.ai_reviewer.exception import customexception
from src.ai_reviewer.logger import logging

class StaticAnalyzer:
    def __init__(self):
        self.complexity_threshold = 5

    def run_all(self, filepath: str) -> List[Issue]:
        """Executes all three static analysis tools and returns combined issues."""
        all_static_issues = []
        all_static_issues.extend(self._run_pylint(filepath))
        all_static_issues.extend(self._run_bandit(filepath))
        all_static_issues.extend(self._run_radon(filepath))
        return all_static_issues

    def _run_pylint(self, filepath: str) -> List[Issue]:
        logging.info(f"Pylint: Analyzing {filepath}")
        json_output = StringIO()
        reporter = JSONReporter(output=json_output)
        args = [filepath, "--disable=C0114,C0115,C0116"]
        
        try:
            Run(args, reporter=reporter, exit=False)
        except Exception as e:
            raise customexception(e, sys)

        results = json.loads(json_output.getvalue()) if json_output.getvalue() else []
        return [
            Issue(
                line=item['line'],
                tool="pylint",
                type=item['type'].upper(),
                msg=item['message']
            ) for item in results
        ]

    def _run_bandit(self, filepath: str) -> List[Issue]:
        logging.info(f"Bandit: Analyzing {filepath}")
        try:
            mgr = BanditManager(BanditConfig(), agg_type='file')
            mgr.discover_files([filepath])
            mgr.run_tests()
            return [
                Issue(
                    line=issue.lineno,
                    tool="bandit",
                    type=issue.severity.upper(),
                    msg=issue.text
                ) for issue in mgr.results
            ]
        except Exception as e:
            raise customexception(e, sys)

    def _run_radon(self, filepath: str) -> List[Issue]:
        """
        Calculates cyclomatic complexity. 
        Added robustness for files with syntax errors.
        """
        logging.info(f"Radon: Analyzing {filepath}")
        issues = []
        try:
            with open(filepath, 'r') as f:
                code_content = f.read()
                if not code_content.strip():
                    return []
                # Attempt to parse the AST for complexity analysis
                tree = ast.parse(code_content)
            
            visitor = ComplexityVisitor.from_ast(tree)
            
            for item in (visitor.functions + visitor.classes):
                if item.complexity > self.complexity_threshold:
                    issues.append(Issue(
                        line=item.lineno,
                        tool="radon",
                        type="MEDIUM",
                        msg=f"{type(item).__name__} '{item.name}' complexity is {item.complexity}"
                    ))
            return issues
        except (SyntaxError, IndentationError):
            # Gracefully handle code that cannot be parsed by the AST
            logging.warning(f"Radon skipped for {filepath} due to syntax errors.")
            return []
        except Exception as e:
            logging.error(f"Unexpected error in Radon analysis: {e}")
            return []