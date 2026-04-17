import os

# --- ENVIRONMENT FIXES (must be before any transformers import) ---
os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "true"
os.environ["HF_HUB_DISABLE_AUTO_CONVERSION"] = "1"

try:
    import transformers.safetensors_conversion as conversion
    conversion.auto_conversion = lambda *args, **kwargs: None
except ImportError:
    pass

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List

from src.ai_reviewer.schemas.review_schema import CodeInput, ReviewOutput
from src.ai_reviewer.pipelines.review_pipeline import ReviewPipeline
from src.ai_reviewer.logger import logging

app = FastAPI(title="AI Code Reviewer API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Lazy Loading Singleton ---
pipeline = None

def get_pipeline():
    global pipeline
    if pipeline is None:
        try:
            logging.info("Initializing AI pipeline...")
            pipeline = ReviewPipeline()
        except Exception as e:
            logging.error(f"Failed to initialize ReviewPipeline: {e}")
            import traceback
            logging.error(traceback.format_exc())
            raise e
    return pipeline


@app.get("/")
def health_check():
    return {"status": "AI Code Reviewer API is running"}


@app.post("/review", response_model=ReviewOutput)
def run_code_review(input: CodeInput):
    try:
        logging.info(f"Review request for: {input.file_name}")
        current_pipeline = get_pipeline()
        review_output = current_pipeline.run(input)
        logging.info(f"Review complete. {len(review_output.issues)} issues found.")
        return review_output
    except Exception as e:
        import traceback
        logging.error(f"Error in /review: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


class FixResponse(BaseModel):
    fixed_code: str
    available: bool


@app.get("/fix", response_model=FixResponse)
def get_fixed_code():
    """
    Returns the complete fixed version of the last reviewed file.
    Called by the VS Code extension when user clicks Apply All Fixes.
    """
    try:
        current_pipeline = get_pipeline()
        fixed_code = current_pipeline.engine.ai_analyzer.last_fixed_code
        if fixed_code:
            logging.info(f"Serving fixed code ({len(fixed_code)} chars).")
            return FixResponse(fixed_code=fixed_code, available=True)
        else:
            return FixResponse(fixed_code="", available=False)
    except Exception as e:
        logging.error(f"Error in /fix: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── PR SIMULATION: Suggest Commit Message ────────────────────────────────────

class CommitRequest(BaseModel):
    fixedFiles: List[str]
    issuesSummary: str


class CommitResponse(BaseModel):
    commitMessage: str


@app.post("/suggest-commit", response_model=CommitResponse)
async def suggest_commit(request: CommitRequest):
    """
    Given the list of AI-fixed files and a summary of issues,
    returns an AI-generated conventional commit message.
    Called by the VS Code extension for the PR Simulation push flow.
    """
    try:
        current_pipeline = get_pipeline()
        groq_client = current_pipeline.engine.ai_analyzer.client

        files_str = ", ".join(request.fixedFiles) if request.fixedFiles else "unknown file"
        issues_str = request.issuesSummary or "various code quality and security issues"

        prompt = f"""You are a Git commit message generator for a professional developer.

A developer used an AI code reviewer to automatically fix issues in their Python code.

Fixed files: {files_str}
Issues that were fixed: {issues_str}

Generate ONE conventional commit message following this exact format:
fix(<scope>): <short description of what was fixed>

Rules:
- Use "fix" as the type
- scope = the filename without extension (e.g. app, db_handler, utils)
- Description must be under 60 characters
- Be specific about what was fixed (e.g. "removed hardcoded password and SQL injection")
- Do NOT include any explanation, just the commit message on one line

Example output:
fix(app): remove hardcoded secret and fix SQL injection vulnerability"""

        response = groq_client.chat.completions.create(
            model="llama3-70b-8192",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=80,
            temperature=0.3
        )

        commit_msg = response.choices[0].message.content.strip()

        # Clean up: remove quotes if model wrapped it
        commit_msg = commit_msg.strip('"').strip("'")

        # Fallback if response is too long or weird
        if len(commit_msg) > 100 or '\n' in commit_msg:
            commit_msg = f"fix: applied AI code review fixes to {files_str}"

        logging.info(f"Suggested commit message: {commit_msg}")
        return CommitResponse(commitMessage=commit_msg)

    except Exception as e:
        logging.error(f"Error in /suggest-commit: {e}")
        # Return a safe fallback instead of 500 error
        files_str = ", ".join(request.fixedFiles) if request.fixedFiles else "code"
        return CommitResponse(
            commitMessage=f"fix: applied AI code review fixes to {files_str}"
        )


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port, timeout_keep_alive=300)