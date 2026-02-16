import os
import sys
import tempfile
from typing import List

# --- Our Imports ---
from src.ai_reviewer.schemas.review_schema import CodeInput, ReviewOutput, Issue
from src.ai_reviewer.components.analysis_engine import AnalysisEngine # <--- Use the Engine class
from src.ai_reviewer.exception import customexception
from src.ai_reviewer.logger import logging

class ReviewPipeline:
    def __init__(self):
        # Initialize the engine once; it will manage all specific analyzers
        self.engine = AnalysisEngine()

    def run(self, code_input: CodeInput) -> ReviewOutput:
        """
        Runs the full analysis pipeline by delegating to the AnalysisEngine.
        """
        logging.info("Review pipeline started.")
        
        try:
            # 1. Create a temporary file for tools that require a physical file path
            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix=".py", 
                delete=False 
            ) as temp_file:
                temp_file.write(code_input.code_content)
                temp_filepath = temp_file.name
                logging.info(f"Code written to temporary file: {temp_filepath}")

            # 2. RUN ANALYSIS VIA THE ENGINE
            # The engine now coordinates AST, Pylint, Bandit, and Radon
            all_issues = self.engine.run_all_analysis(
                code_input.code_content, 
                temp_filepath
            )
            
            logging.info(f"Total issues found across all tools: {len(all_issues)}")

            # 3. Prepare the final output
            return ReviewOutput(
                status="success",
                file_name=code_input.file_name,
                issues=all_issues
            )

        except Exception as e:
            logging.error(f"Error in review pipeline: {str(e)}")
            raise customexception(e, sys)
            
        finally:
            # 4. Clean up the temporary file
            if 'temp_filepath' in locals() and os.path.exists(temp_filepath):
                os.remove(temp_filepath)
                logging.info(f"Temporary file {temp_filepath} deleted.")