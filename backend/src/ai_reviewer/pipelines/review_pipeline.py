import os
import sys
import tempfile
from typing import List

# --- Our Imports ---
from src.ai_reviewer.schemas.review_schema import CodeInput, ReviewOutput, Issue
from src.ai_reviewer.components.analysis_engine import AnalysisEngine 
from src.ai_reviewer.exception import customexception
from src.ai_reviewer.logger import logging

class ReviewPipeline:
    def __init__(self):
        # Initialize the engine (which now internally handles BOTH static and AI analysis)
        self.engine = AnalysisEngine()

    def run(self, code_input: CodeInput) -> ReviewOutput:
        """
        Runs the full analysis pipeline by delegating to the AnalysisEngine.
        """
        logging.info("Review pipeline started.")
        
        try:
            # 1. Create a temporary file for physical file path tools (Pylint, Bandit)
            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix=".py", 
                delete=False 
            ) as temp_file:
                temp_file.write(code_input.code_content)
                temp_filepath = temp_file.name
                logging.info(f"Code written to temporary file: {temp_filepath}")

            # 2. RUN ALL ANALYSIS 
            # The engine returns both static and AI issues together now
            raw_issues = self.engine.run_all_analysis(
                code_input.code_content, 
                temp_filepath
            )
            
            # 3. FUSION & CONFIDENCE ENGINE 
            # Filter out common AI hallucinations like 'converged' 
            all_issues = self._fuse_results(raw_issues)
            
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

    def _fuse_results(self, raw_list: List[Issue]) -> List[Issue]:
        """
        Filters results and removes garbage AI output.
        """
        final_list = []
        
        for issue in raw_list:
            # CLEANUP: Remove suggestions that contain the "converged" error text
            if "converged" in issue.msg.lower():
                logging.warning(f"Filtered out low-confidence AI issue on line {issue.line}")
                continue
            
            final_list.append(issue)
            
        return final_list