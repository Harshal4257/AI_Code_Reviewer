from fastapi import FastAPI, HTTPException, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import sys

# --- Our Imports ---
from src.ai_reviewer.schemas.review_schema import CodeInput, ReviewOutput
from src.ai_reviewer.pipelines.review_pipeline import ReviewPipeline
from src.ai_reviewer.exception import customexception
from src.ai_reviewer.logger import logging

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
# We set this to None so the server starts up instantly without using much RAM.
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
            print(traceback.format_exc())
            raise e
    return pipeline

@app.get("/")
def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/review", response_model=ReviewOutput)
def run_code_review(input: CodeInput):
    """
    This endpoint now triggers the model loading only on the first request.
    """
    try:
        logging.info(f"Received review request for file: {input.file_name}")
        
        # Get the pipeline (loads models on 1st request, returns cached one after)
        current_pipeline = get_pipeline()
        
        review_output = current_pipeline.run(input)
        
        logging.info(f"Review successful. Found {len(review_output.issues)} issues.")
        return review_output

    except Exception as e:
        import traceback
        print(traceback.format_exc()) 
        logging.error(f"Error during /review endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    # Added timeout_keep_alive to prevent connection drops during heavy AI loading
    uvicorn.run(app, host="127.0.0.1", port=8001, timeout_keep_alive=60)