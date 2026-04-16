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

        - ASTAnalyzer     : structural analysis (function length, arg count, naming)
        - StaticAnalyzer  : Pylint, Bandit, Radon static analysis tools
        - AIAnalyzer      : PRIMARY — Groq LLaMA-3 70B + AST pre-scan
                            FALLBACK — CodeBERT + CodeT5+ (lazy loaded if Groq unavailable)
        """
        logging.info("Initializing Analysis Engine components...")
        self.ast_analyzer = ASTAnalyzer()
        self.static_analyzer = StaticAnalyzer()
        self.ai_analyzer = AIAnalyzer()

    def run_all_analysis(self, code_content: str, filepath: str) -> List[Issue]:
        """
        Runs the full analysis pipeline:

        Step 1 — AST structural analysis (function complexity, naming)
        Step 2 — Static tools: Pylint, Bandit, Radon
        Step 3 — AI deep analysis:
                   • Pre-scan (AST + Regex) catches deterministic bugs
                   • Groq LLaMA-3 70B catches logic bugs, missing guards, bad practices
                   • Falls back to CodeBERT + CodeT5+ if Groq API key is not set
        """
        all_issues: List[Issue] = []

        # Step 1: AST Structural Analysis
        logging.info("Running AST structural analysis...")
        try:
            self.ast_analyzer.analyze(code_content)
        except Exception as e:
            logging.warning(f"AST analysis skipped: {e}")

        # Step 2: Static Tool Analysis (Pylint, Bandit, Radon)
        logging.info("Running static analysis tools...")
        try:
            self.static_analyzer.run_all(filepath)
        except Exception as e:
            logging.warning(f"Static analysis skipped: {e}")

        # Step 3: AI Deep Analysis (Groq primary / CodeBERT+CodeT5+ fallback)
        logging.info("Running AI deep analysis...")
        try:
            ai_raw_issues = self.ai_analyzer.analyze(code_content)
            for i in ai_raw_issues:
                all_issues.append(Issue(
                    line=i.get("line", 1),
                    tool=i["tool"],
                    type=i["type"],
                    msg=i["msg"],
                    category=i.get("category", "warning")
                ))
        except Exception as e:
            logging.error(f"AI Analysis failed: {e}")

        logging.info(f"Analysis complete. Total issues: {len(all_issues)}")
        return all_issues