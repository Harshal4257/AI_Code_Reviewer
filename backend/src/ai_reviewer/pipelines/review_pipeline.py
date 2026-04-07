import os
import sys
import tempfile
from typing import List

from src.ai_reviewer.schemas.review_schema import CodeInput, ReviewOutput, Issue
from src.ai_reviewer.components.analysis_engine import AnalysisEngine
from src.ai_reviewer.exception import customexception
from src.ai_reviewer.logger import logging


class ReviewPipeline:
    def __init__(self):
        self.engine = AnalysisEngine()

    def run(self, code_input: CodeInput) -> ReviewOutput:
        logging.info("Review pipeline started.")

        try:
            # Normalize line endings to LF to avoid pylint CRLF errors on Windows
            normalized_code = code_input.code_content.replace('\r\n', '\n').replace('\r', '\n')

            # Write temp file with explicit LF endings
            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix=".py",
                delete=False,
                newline='\n',       # Force LF on Windows
                encoding='utf-8'
            ) as temp_file:
                temp_file.write(normalized_code)
                temp_filepath = temp_file.name
                logging.info(f"Code written to temp file: {temp_filepath}")

            raw_issues = self.engine.run_all_analysis(normalized_code, temp_filepath)
            all_issues = self._fuse_results(raw_issues)

            logging.info(f"Total issues found: {len(all_issues)}")

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
                logging.info(f"Temp file {temp_filepath} deleted.")

    def _fuse_results(self, raw_list: List[Issue]) -> List[Issue]:
        final_list = []
        seen = set()  # Deduplicate identical messages on the same line

        for issue in raw_list:
            # Remove hallucinated AI output
            if "converged" in issue.msg.lower():
                continue
            if "FULL_FILE_FIX_AVAILABLE" in issue.msg:
                # Always keep this signal — do not filter it out
                final_list.append(issue)
                continue

            # Deduplicate — same tool + same line + same message
            key = (issue.tool, issue.line, issue.msg[:50])
            if key in seen:
                continue
            seen.add(key)

            final_list.append(issue)

        return final_list