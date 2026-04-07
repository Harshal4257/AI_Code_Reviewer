from pydantic import BaseModel
from typing import List, Optional


class CodeInput(BaseModel):
    """Schema for the code received from the IDE."""
    language: str
    code_content: str
    file_name: str


class Issue(BaseModel):
    """A single issue found by any analyzer."""
    line: int
    tool: str
    type: str
    msg: str
    category: Optional[str] = "warning"  # "security" | "error" | "warning"


class ReviewOutput(BaseModel):
    """The final JSON report sent back to the IDE."""
    status: str
    file_name: Optional[str] = None
    issues: List[Issue]