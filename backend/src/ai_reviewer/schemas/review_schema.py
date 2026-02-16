from pydantic import BaseModel
from typing import List, Optional

class CodeInput(BaseModel):
    """Schema for the code we receive from the IDE."""
    language: str
    code_content: str 
    file_name: str # Added to match extension.ts payload

class Issue(BaseModel):
    """A single issue found by any tool."""
    line: int      # Changed from line_number to match analyzers/extension
    tool: str  
    type: str      # Added to match StaticAnalyzer
    msg: str       # Changed from message to match StaticAnalyzer

class ReviewOutput(BaseModel):
    """The final JSON report we send back to the IDE."""
    status: str
    file_name: str
    issues: List[Issue]