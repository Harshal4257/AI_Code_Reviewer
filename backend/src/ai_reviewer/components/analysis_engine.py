from typing import List
from src.ai_reviewer.schemas.review_schema import Issue
from src.ai_reviewer.analyzers.ast_analyzer import ASTAnalyzer
from src.ai_reviewer.analyzers.static_analyzer import StaticAnalyzer
from src.ai_reviewer.analyzers.ai_analyzer import AIAnalyzer
from src.ai_reviewer.logger import logging


class AnalysisEngine:
    def __init__(self):
        """
        Initializes all analyzer components:
        - ASTAnalyzer     : structural code analysis (function length, arg count, naming)
        - StaticAnalyzer  : Pylint, Bandit, Radon static analysis tools
        - AIAnalyzer      : Groq LLaMA-3 70B + AST pre-scan — primary engine
        """
        logging.info("Initializing Analysis Engine components...")
        self.ast_analyzer = ASTAnalyzer()
        self.static_analyzer = StaticAnalyzer()
        self.ai_analyzer = AIAnalyzer()

    def run_all_analysis(self, code_content: str, filepath: str) -> List[Issue]:
        """
        Runs the complete analysis pipeline.

        Architecture:
        - AST and static tools (Pylint, Bandit, Radon) are initialized and available.
        - AIAnalyzer runs an internal AST pre-scan + Groq LLaMA-3 70B for deep analysis.
        - Pre-scan catches deterministic bugs (operator errors, secrets, unclosed files).
        - Groq catches remaining issues (logic bugs, missing guards, bad practices).
        - Single source of truth eliminates duplicate/conflicting results.
        """
        all_issues: List[Issue] = []

        # --- Step 1: AST Structural Analysis ---
        logging.info("Running AST structural analysis...")
        try:
            self.ast_analyzer.analyze(code_content)
        except Exception as e:
            logging.warning(f"AST analysis skipped: {e}")

        # --- Step 2: Static Tool Analysis ---
        logging.info("Running static analysis tools (Pylint, Bandit, Radon)...")
        try:
            self.static_analyzer.run_all(filepath)
        except Exception as e:
            logging.warning(f"Static analysis skipped: {e}")

        # --- Step 3: AI Deep Analysis (Pre-scan + Groq LLaMA-3 70B) ---
        logging.info("Running AI deep analysis (AST pre-scan + Groq LLaMA-3 70B)...")
        try:
            ai_raw_issues = self.ai_analyzer.analyze(code_content)
            for i in ai_raw_issues:
                all_issues.append(Issue(
                    line=i.get("line", 1),
                    tool=i["tool"],
                    type=i["type"],
                    msg=i["msg"],
                    category=i.get("category", "warning")  # pass category for color coding
                ))
        except Exception as e:
            logging.error(f"AI Analysis failed: {e}")

        logging.info(f"Analysis complete. Total issues: {len(all_issues)}")
        return all_issues