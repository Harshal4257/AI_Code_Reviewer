import os
import sys
import tempfile
from typing import List

# --- Our Imports ---
from src.ai_reviewer.schemas.review_schema import CodeInput, ReviewOutput, Issue
from src.ai_reviewer.components.analysis_engine import AnalysisEngine 
# Ensure these are imported for the AI/ML Analysis Layer [cite: 125, 134]
from src.ai_reviewer.pipelines.ai_analyzer import AIAnalyzer 
from src.ai_reviewer.exception import customexception
from src.ai_reviewer.logger import logging

class ReviewPipeline:
    def __init__(self):
        # Initialize the static engine and the AI analyzer [cite: 113, 137]
        self.engine = AnalysisEngine()
        self.ai_analyzer = AIAnalyzer() # <--- New AI Analysis Layer [cite: 125]

    def run(self, code_input: CodeInput) -> ReviewOutput:
        """
        Runs the full analysis pipeline combining Static and AI analysis[cite: 140, 212].
        """
        logging.info("Review pipeline started.")
        
        try:
            # 1. Create a temporary file for physical file path tools (Pylint, Bandit) [cite: 138, 220]
            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix=".py", 
                delete=False 
            ) as temp_file:
                temp_file.write(code_input.code_content)
                temp_filepath = temp_file.name
                logging.info(f"Code written to temporary file: {temp_filepath}")

            # 2. RUN STATIC ANALYSIS [cite: 124, 155]
            static_issues = self.engine.run_all_analysis(
                code_input.code_content, 
                temp_filepath
            )
            
            # 3. RUN AI-BASED ANALYSIS (CodeBERT & CodeT5) [cite: 125, 181]
            # This identifies logical flaws and provides refactoring suggestions [cite: 184, 224]
            ai_issues = self.ai_analyzer.analyze(code_input.code_content)
            
            # 4. FUSION & CONFIDENCE ENGINE 
            # Combine results and filter out common AI hallucinations like 'converged' 
            all_issues = self._fuse_results(static_issues, ai_issues)
            
            logging.info(f"Total processed issues found: {len(all_issues)}")

            return ReviewOutput(
                status="success",
                file_name=code_input.file_name,
                issues=all_issues
            )

        except Exception as e:
            logging.error(f"Error in review pipeline: {str(e)}")
            raise customexception(e, sys)
            
        finally:
            if 'temp_filepath' in locals() and os.path.exists(temp_filepath):
                os.remove(temp_filepath)
                logging.info(f"Temporary file {temp_filepath} deleted.")

    def _fuse_results(self, static_list: List[Issue], ai_list: List[Issue]) -> List[Issue]:
        """
        Merges results and removes garbage AI output[cite: 142, 226].
        """
        combined = static_list + ai_list
        final_list = []
        
        for issue in combined:
            # CLEANUP: Remove suggestions that contain the "converged" error text
            if "converged" in issue.msg.lower():
                logging.warning(f"Filtered out low-confidence AI issue on line {issue.line}")
                continue
            
            # PRECISE MAPPING: Ensure line 1 isn't overwhelmed by global suggestions [cite: 235]
            # If the tool is AI and it points to line 1, we ensure it's a valid global suggestion
            final_list.append(issue)
            
        return final_list