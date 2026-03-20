import os
# --- STAGE 0: ENVIRONMENT & BACKGROUND THREAD FIXES ---
# Must be at the very top to block the 'auto_conversion' thread and PR creation
os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "true"
os.environ["SAFETENSORS_FAST_GPU"] = "1"
os.environ["HF_HUB_DISABLE_AUTO_CONVERSION"] = "1"

# Monkey-patching the conversion function to hard-block the failing thread
try:
    import transformers.safetensors_conversion as conversion
    conversion.auto_conversion = lambda *args, **kwargs: None 
except ImportError:
    pass

from fastapi import FastAPI, HTTPException, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import transformers # Added to control logging verbosity

# --- Our Imports ---
from src.ai_reviewer.schemas.review_schema import CodeInput, ReviewOutput
from src.ai_reviewer.pipelines.review_pipeline import ReviewPipeline
from src.ai_reviewer.logger import logging

# Mute standard library warnings for a cleaner console
transformers.utils.logging.set_verbosity_error()

app = FastAPI(
    title="AI Code Reviewer & PR Assistant API",
    version="0.0.1"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- PERMANENT FIX: Lazy Loading Singleton ---
pipeline = None

def get_pipeline():
    """
    Helper function to load the pipeline only when needed.
    """
    global pipeline
    if pipeline is None:
        try:
            logging.info("Lazy Loading AI models for the first time...")
            pipeline = ReviewPipeline()
        except Exception as e:
            logging.error(f"Failed to initialize ReviewPipeline during lazy load: {e}")
            import traceback
            logging.error(traceback.format_exc())
            raise e
    return pipeline

@app.get("/")
def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/review", response_model=ReviewOutput)
def run_code_review(input: CodeInput):
    """
    This endpoint triggers the model loading only on the first request.
    """
    try:
        logging.info(f"Received review request for file: {input.file_name}")
        
        current_pipeline = get_pipeline()
        review_output = current_pipeline.run(input)
        
        logging.info(f"Review successful. Found {len(review_output.issues)} issues.")
        return review_output

    except Exception as e:
        import traceback
        logging.error(f"Error during /review endpoint: {e}")
        logging.error(traceback.format_exc()) 
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    # 127.0.0.1 is more stable for VS Code extensions on Windows
    # Increased keep-alive to 300s to handle long model loading times
    uvicorn.run(
        app, 
        host="127.0.0.1", 
        port=8001, 
        timeout_keep_alive=300
    )