from pydantic import BaseModel
from typing import List, Optional

class CodeInput(BaseModel):
    """Schema for the code we receive from the IDE."""
    language: str
    code_content: str 
    file_name: str 

class Issue(BaseModel):
    """A single issue found by any tool."""
    line: int      
    tool: str  
    type: str      
    msg: str       

class ReviewOutput(BaseModel):
    """The final JSON report we send back to the IDE."""
    status: str
    # CHANGED: Optional prevents 500 errors if the filename is missing
    file_name: Optional[str] = None 
    issues: List[Issue]