from typing import List
from src.ai_reviewer.schemas.review_schema import Issue
from src.ai_reviewer.analyzers.ast_analyzer import ASTAnalyzer
from src.ai_reviewer.analyzers.static_analyzer import StaticAnalyzer
from src.ai_reviewer.analyzers.ai_analyzer import AIAnalyzer  # <--- UNCOMMENTED
from src.ai_reviewer.logger import logging

class AnalysisEngine:
    def __init__(self):
        # Initializing the individual analyzers
        logging.info("Initializing Analysis Engine components...")
        self.ast_analyzer = ASTAnalyzer()
        self.static_analyzer = StaticAnalyzer()
        self.ai_analyzer = AIAnalyzer() # <--- NOW ACTIVE

    def run_all_analysis(self, code_content: str, filepath: str) -> List[Issue]:
        """
        Coordinates the execution of different analyzer modules: 
        AST, Static Tools, and AI Models.
        """
        all_issues: List[Issue] = []
        
        # 1. Structural Analysis (AST)
        logging.info("Starting AST analysis...")
        raw_ast_data = self.ast_analyzer.analyze(code_content)
        for i in raw_ast_data:
            all_issues.append(Issue(
                line=i.get("line", 1),
                tool=i["tool"],
                type=i["type"],
                msg=i["msg"]
            ))
        
        # 2. Tool-based Analysis (Pylint, Bandit, Radon)
        logging.info("Starting Static tool analysis...")
        static_issues = self.static_analyzer.run_all(filepath)
        all_issues.extend(static_issues)
        
        # 3. AI/LLM Analysis (CodeT5 + CodeBERT)
        logging.info("Starting AI/LLM analysis...")
        try:
            ai_raw_issues = self.ai_analyzer.analyze(code_content)
            for i in ai_raw_issues:
                all_issues.append(Issue(
                    line=i.get("line", 1),
                    tool=i["tool"],
                    type=i["type"],
                    msg=i["msg"]
                ))
        except Exception as e:
            logging.error(f"AI Analysis failed to integrate: {e}")
        
        return all_issues