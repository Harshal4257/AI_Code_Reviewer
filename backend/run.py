import subprocess
import sys
import json
from io import StringIO

# --- PYLINT IMPORTS ---
from pylint.lint import Run
from pylint.reporters.json_reporter import JSONReporter

# --- BANDIT IMPORTS ---
from bandit.core.manager import BanditManager
from bandit.core.config import BanditConfig

# --- RADON IMPORTS ---
import ast # Built-in Python module
from radon.visitors import ComplexityVisitor

# The file we want to analyze
FILE_TO_ANALYZE = "test_code.py"

def run_pylint(filepath):
    print("--- 1. RUNNING PYLINT (as a library) ---")
    
    json_output_stream = StringIO()
    reporter = JSONReporter(output=json_output_stream)
    
    pylint_args = [
        filepath,
        "--disable=C0114,C0115,C0116" # Disables "missing docstring"
    ]

    try:
        Run(pylint_args, reporter=reporter)
    except SystemExit:
        # Pylint's 'Run' exits by default. We catch it here.
        pass
    except Exception as e:
        print(f"An error occurred running Pylint: {e}")

    # Get the value *after* the try/except block
    json_string = json_output_stream.getvalue()
    
    if json_string:
        try:
            issues = json.loads(json_string)
            if not issues:
                print("Pylint found no issues.")
            else:
                print(f"Pylint found {len(issues)} issues:")
                for issue in issues:
                    print(f"  - [Line {issue['line']}] {issue['message-id']} ({issue['symbol']})")
                    print(f"    Message: {issue['message']}\n")
        except json.JSONDecodeError:
            print(f"Pylint output invalid JSON: {json_string}")
    else:
        print("Pylint ran successfully, but produced no output.")
        
    json_output_stream.close()
    print("----------------------------------------\n")


def run_bandit(filepath):
    print("--- 2. RUNNING BANDIT (as a library) ---")
    try:
        config = BanditConfig()
        manager = BanditManager(config, agg_type='file')
        
        manager.discover_files([filepath])
        manager.run_tests()
        
        if not manager.results:
            print("Bandit found no issues.")
            print("----------------------------------------\n")
            return
            
        print(f"Bandit found {len(manager.results)} issues:")
        for issue in manager.results:
            # --- THIS IS THE FIX ---
            # It's 'issue.text', not 'issue.issue_text'
            print(f"  - [Line {issue.lineno}] {issue.test_id} ({issue.severity})")
            print(f"    Message: {issue.text}\n") 
            
    except Exception as e:
        print(f"An error occurred running Bandit: {e}")
    print("----------------------------------------\n")


def run_radon(filepath):
    print("--- 3. RUNNING RADON (as a library) ---")
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            code = f.read()
        
        tree = ast.parse(code)
        visitor = ComplexityVisitor.from_ast(tree)
        
        # --- THIS IS THE FIX ---
        # We loop through the .functions and .classes lists separately
        # so we know the type of each item.
        results = visitor.functions + visitor.classes
        
        if not results:
            print("Radon could not find any functions/classes to analyze.")
            print("-----------------------------------------\n")
            return
            
        print("Radon Complexity Analysis:")
        
        # Loop 1: Functions
        for item in visitor.functions:
            print(f"  - Function '{item.name}' [Line {item.lineno}]: Complexity {item.complexity}")
            
        # Loop 2: Classes
        for item in visitor.classes:
            print(f"  - Class '{item.name}' [Line {item.lineno}]: Complexity {item.complexity}")
            
    except SyntaxError as e:
        print(f"Radon Error: Could not parse {filepath}. Invalid Python syntax.")
        print(f"  Details: {e}")
    except Exception as e:
        print(f"An error occurred running Radon: {e}")
    print("-----------------------------------------\n")


if __name__ == "__main__":
    print(f"Starting analysis on: {FILE_TO_ANALYZE}\n")
    run_pylint(FILE_TO_ANALYZE)
    run_bandit(FILE_TO_ANALYZE)
    run_radon(FILE_TO_ANALYZE)
    print("Analysis complete.")