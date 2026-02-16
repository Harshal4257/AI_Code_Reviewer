import os
from pathlib import Path

# 1. Set our package name
package_name = "ai_reviewer"

# 2. Define our project's file structure
list_of_files = [
    ".github/workflows/.gitkeep",
    f"src/{package_name}/__init__.py",
    f"src/{package_name}/components/__init__.py",
    f"src/{package_name}/components/analysis_engine.py", # Our engine (Pylint, Bandit, Radon)
    f"src/{package_name}/pipelines/__init__.py",
    f"src/{package_name}/pipelines/review_pipeline.py",  # Coordinates the components
    f"src/{package_name}/schemas/__init__.py",
    f"src/{package_name}/schemas/review_schema.py",    # Our Pydantic models
    f"src/{package_name}/utils/__init__.py",
    f"src/{package_name}/utils/common.py",             # Utility functions
    f"src/{package_name}/logger.py",
    f"src/{package_name}/exception.py",
    "app.py",                                          # Our FastAPI server
    "requirements.txt",
    "setup.py",
    ".gitignore",
    "test_code.py"                                     # The test file we've been using
]

# 3. The logic to create the files and directories (same as your script)
for filepath in list_of_files:
    filepath = Path(filepath)
    filedir, filename = os.path.split(filepath)
    
    # Create the directory if it doesn't exist
    if filedir != "":
        os.makedirs(filedir, exist_ok=True)
        print(f"Creating directory: {filedir}")
        
    # Create the file if it doesn't exist or is empty
    if (not os.path.exists(filepath)) or (os.path.getsize(filepath) == 0):
        with open(filepath, "w") as f:
            pass # Create an empty file
            print(f"Creating empty file: {filepath}")
    else:
        print(f"File already exists: {filepath}")