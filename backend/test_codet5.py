import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.ai_reviewer.analyzers.ai_analyzer import AIAnalyzer

analyzer = AIAnalyzer()
code = """
def check_status(is_active):
    if is_active == True:
        print("System is live")
"""
lines = code.split('\n')
issues = analyzer.analyze(code, error_lines=[3])

print("ISSUES:", issues)
