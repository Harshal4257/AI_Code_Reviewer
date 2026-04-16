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

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port, timeout_keep_alive=300)