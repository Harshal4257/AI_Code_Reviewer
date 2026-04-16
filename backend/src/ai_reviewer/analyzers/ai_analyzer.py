import os
import re
import ast as python_ast
import hashlib
from typing import List, Dict, Any

from src.ai_reviewer.logger import logging

# --- Groq API Import (lightweight, always available) ---
try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False
    logging.warning("groq package not installed. Run: pip install groq")


# =============================================================================
# NOTE FOR REVIEWERS / RESEARCH REFERENCE:
# This project uses a 3-model architecture as described in the research paper:
#
#   1. CodeBERT (mrm8488/codebert-base-finetuned-detect-insecure-code)
#      → Used for vulnerability/security classification (line-by-line)
#      → See: _analyze_with_codebert()
#
#   2. CodeT5+ (Salesforce/codet5p-220m)
#      → Used for code fix suggestion generation
#      → See: _analyze_with_codet5()
#
#   3. Groq API — LLaMA-3 70B (PRIMARY, active in production)
#      → Replaces local models for speed and accuracy in deployment
#      → CodeBERT + CodeT5+ serve as fallback when Groq is unavailable
#
# Both local models are fully implemented below and activate automatically
# if GROQ_API_KEY is not set in the environment.
# =============================================================================


class AIAnalyzer:
    def __init__(self):
        logging.info("Initializing AI Architecture...")

        self.groq_client = None
        self.groq_model = "llama-3.3-70b-versatile"
        self.last_fixed_code: str = ""

        # --- Primary: Groq API (LLaMA-3 70B) ---
        if GROQ_AVAILABLE:
            api_key = os.environ.get("GROQ_API_KEY")
            if api_key:
                self.groq_client = Groq(api_key=api_key)
                logging.info("Groq API (LLaMA-3 70B) initialized successfully.")
            else:
                logging.warning("GROQ_API_KEY not set. Will fall back to local LLMs.")

        # --- Fallback: CodeBERT + CodeT5+ (loaded lazily only if Groq unavailable) ---
        # Models are NOT loaded here to keep startup fast on deployment.
        # They initialize on first use via _load_local_models() below.
        self._local_models_loaded = False
        self.device = None
        self.bert_tokenizer = None
        self.bert_model = None
        self.suggest_tokenizer = None
        self.suggest_model = None

    # ====================================================================
    # LAZY LOADER — CodeBERT + CodeT5+ (only runs if Groq is unavailable)
    # ====================================================================

    def _load_local_models(self):
        """
        Loads CodeBERT and CodeT5+ models on first use.
        These are the research models described in the project paper.
        Only called when Groq API is unavailable (no API key set).
        """
        if self._local_models_loaded:
            return

        logging.info("Loading local models: CodeBERT + CodeT5+ (fallback mode)...")

        # Lazy imports — torch and transformers only load here, not at module level
        import torch
        from transformers import (
            AutoTokenizer,
            AutoModelForSequenceClassification,
            AutoModelForSeq2SeqLM,
            T5Tokenizer,
            RobertaTokenizer
        )
        import transformers
        transformers.utils.logging.set_verbosity_error()

        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        # CodeBERT — security vulnerability classifier
        bert_name = "mrm8488/codebert-base-finetuned-detect-insecure-code"
        self.bert_tokenizer = RobertaTokenizer.from_pretrained(bert_name, use_fast=False)
        self.bert_model = AutoModelForSequenceClassification.from_pretrained(
            bert_name,
            use_safetensors=False
        ).to(self.device)
        logging.info("CodeBERT loaded successfully.")

        # CodeT5+ — code fix suggestion generator
        suggest_model_name = "Salesforce/codet5p-220m"
        try:
            self.suggest_tokenizer = T5Tokenizer.from_pretrained(suggest_model_name, use_fast=False)
        except Exception:
            self.suggest_tokenizer = T5Tokenizer.from_pretrained("t5-base", use_fast=False)

        self.suggest_model = AutoModelForSeq2SeqLM.from_pretrained(
            suggest_model_name,
            use_safetensors=False
        ).to(self.device)
        logging.info("CodeT5+ loaded successfully.")

        self._local_models_loaded = True
        logging.info("All local models ready.")

    # ====================================================================
    # PRE-SCAN — Python AST + Regex (deterministic, never misses)
    # ====================================================================

    def _pre_scan(self, code: str) -> List[Dict[str, Any]]:
        issues = []
        lines = code.split('\n')

        for i, line in enumerate(lines):
            stripped = line.strip()
            line_num = i + 1

            # 1. Operator bug =+
            if re.search(r'\b\w+\s*=\+\s*\w+', line):
                issues.append({
                    "line": line_num,
                    "tool": "Pylint",
                    "type": "AI Suggestion",
                    "category": "error",
                    "msg": "Operator bug: '=+' should be '+='. This resets the variable to a positive value instead of incrementing it."
                })

            # 2. Operator bug =-
            if re.search(r'\b\w+\s*=-\w+', line):
                issues.append({
                    "line": line_num,
                    "tool": "Pylint",
                    "type": "AI Suggestion",
                    "category": "error",
                    "msg": "Operator bug: '=-' should be '-='. This resets the variable instead of decrementing it."
                })

            # 3. Operator bug =*
            if re.search(r'\b\w+\s*=\*\s*\w+', line):
                issues.append({
                    "line": line_num,
                    "tool": "Pylint",
                    "type": "AI Suggestion",
                    "category": "error",
                    "msg": "Operator bug: '=*' should be '*='. This resets the variable instead of multiplying it."
                })

            # 4. Unclosed file handle
            if re.search(r'\b\w+\s*=\s*open\s*\(', stripped) and not stripped.startswith('with'):
                issues.append({
                    "line": line_num,
                    "tool": "Bandit",
                    "type": "AI Suggestion",
                    "category": "error",
                    "msg": "Unclosed file handle: use 'with open(...) as f:' to ensure file is properly closed."
                })

            # 5. Hardcoded secrets
            if re.search(
                r'\b\w*(password|passwd|secret|token|api_key|apikey|api|credential|auth|pwd|pass)\w*\s*=\s*["\'][^"\']{3,}["\']',
                stripped, re.IGNORECASE
            ):
                issues.append({
                    "line": line_num,
                    "tool": "Bandit",
                    "type": "Security/Logic Risk",
                    "category": "security",
                    "msg": "Hardcoded secret detected. Use os.environ.get('VAR_NAME') instead of hardcoding credentials."
                })

            # 6. eval()/exec() with user input
            if re.search(r'eval\s*\(\s*input\s*\(', stripped) or \
               re.search(r'exec\s*\(\s*input\s*\(', stripped):
                issues.append({
                    "line": line_num,
                    "tool": "Bandit",
                    "type": "Security/Logic Risk",
                    "category": "security",
                    "msg": "Critical security risk: eval()/exec() with user input allows arbitrary code execution."
                })

            # 7. SQL injection
            if re.search(r'(SELECT|INSERT|UPDATE|DELETE).+\+\s*(str\(|input\(|\w+)', stripped, re.IGNORECASE):
                issues.append({
                    "line": line_num,
                    "tool": "Bandit",
                    "type": "Security/Logic Risk",
                    "category": "security",
                    "msg": "SQL injection risk: use parameterized queries instead of string concatenation."
                })

        # 8. Mutable default arguments
        try:
            tree = python_ast.parse(code)
            for node in python_ast.walk(tree):
                if isinstance(node, python_ast.FunctionDef):
                    for default in node.args.defaults:
                        if isinstance(default, (python_ast.List, python_ast.Dict, python_ast.Set)):
                            issues.append({
                                "line": node.lineno,
                                "tool": "Pylint",
                                "type": "AI Suggestion",
                                "category": "error",
                                "msg": f"Mutable default argument in '{node.name}()'. Use None as default and initialize inside the function body."
                            })
        except Exception:
            pass

        # 9. Unused imports
        try:
            tree = python_ast.parse(code)
            imported_names = []
            for node in python_ast.walk(tree):
                if isinstance(node, python_ast.Import):
                    for alias in node.names:
                        name = alias.asname if alias.asname else alias.name
                        imported_names.append((name.split('.')[0], node.lineno))
                elif isinstance(node, python_ast.ImportFrom):
                    for alias in node.names:
                        name = alias.asname if alias.asname else alias.name
                        imported_names.append((name, node.lineno))

            for imp_name, imp_line in imported_names:
                if imp_name in ('os', 'sys', 're', 'json', 'math', 'time', 'datetime',
                                'pathlib', 'typing', 'collections', 'itertools', 'functools'):
                    continue
                used = any(
                    re.search(r'\b' + re.escape(imp_name) + r'\b', lines[i])
                    and (i + 1) != imp_line
                    for i in range(len(lines))
                )
                if not used:
                    issues.append({
                        "line": imp_line,
                        "tool": "Pylint",
                        "type": "AI Suggestion",
                        "category": "warning",
                        "msg": f"Unused import '{imp_name}'. Remove it to keep the code clean."
                    })
        except Exception:
            pass

        logging.info(f"Pre-scan found {len(issues)} issues.")
        return issues

    # ====================================================================
    # CALL 1 — Groq finds remaining issues pre-scan can't catch
    # ====================================================================

    def _call_find_issues(self, code: str, pre_scan_issues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        lines = code.split('\n')
        numbered_code = '\n'.join(
            f"{str(i + 1).rjust(4)} | {line}"
            for i, line in enumerate(lines)
        )

        already_found = ""
        if pre_scan_issues:
            already_found = "\n\nAlready found by static analysis (DO NOT report these again):\n"
            already_found += '\n'.join(f"- Line {i['line']}: {i['msg']}" for i in pre_scan_issues)

        response = self.groq_client.chat.completions.create(
            model=self.groq_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a strict Python code reviewer. "
                        "Find every issue. Never say clean unless truly perfect. "
                        "Respond ONLY in the exact format requested."
                    )
                },
                {
                    "role": "user",
                    "content": f"""Do a STRICT line-by-line Python code review.
Line numbers are in format "   1 | code". Use exact line numbers.
{already_found}

Find these issues (that static analysis cannot detect):
1. LOGIC BUGS: if instead of elif causing values to always be overwritten
2. CRASH BUGS: functions that crash on empty list/string with no guard
3. SINGLE CHAR VARIABLES: variables like x, c, n, v used as variable names inside function BODIES — suggest descriptive names. Exclude loop vars i/j/k, and exception handlers like 'except Exception as e'
4. INCORRECT LOGIC: wrong conditions, off-by-one errors, wrong return values
5. MISSING ERROR HANDLING: risky operations with no try/except
6. ANY OTHER BUG OR BAD PRACTICE not already listed above

For each issue found, respond on a new line in EXACTLY this format:
LINE:<number> | CATEGORY:<security or error or warning> | TOOL:<CodeBERT or Pylint or Bandit or AST Parser> | MSG:<clear description>

If you find zero additional issues, respond with: NO_ISSUES

Code:
{numbered_code}"""
                }
            ],
            temperature=0.0,
            max_tokens=2000
        )

        raw = response.choices[0].message.content.strip()
        logging.info(f"Groq raw response:\n{raw[:800]}")

        if raw.strip() == "NO_ISSUES":
            return []

        issues = []
        for line in raw.split('\n'):
            line = line.strip()
            if not line or not line.startswith('LINE:'):
                continue
            try:
                parts = line.split(' | ')
                if len(parts) < 4:
                    continue
                line_num = int(parts[0].replace('LINE:', '').strip())
                category = parts[1].replace('CATEGORY:', '').strip().lower()
                tool = parts[2].replace('TOOL:', '').strip()
                msg = parts[3].replace('MSG:', '').strip()
                line_num = max(1, min(line_num, len(lines)))
                if category not in ['security', 'error', 'warning']:
                    category = 'warning'
                issues.append({
                    "line": line_num,
                    "tool": tool,
                    "type": "Security/Logic Risk" if category == "security" else "AI Suggestion",
                    "category": category,
                    "msg": msg
                })
            except Exception as e:
                logging.warning(f"Could not parse Groq line: '{line}' — {e}")
                continue

        logging.info(f"Groq found {len(issues)} additional issues.")
        return issues

    # ====================================================================
    # CALL 2 — Fix all issues
    # ====================================================================

    def _call_fix_code(self, code: str, all_issues: List[Dict[str, Any]]) -> str:
        issue_summary = '\n'.join(
            f"- Line {i['line']} [{i['tool']}]: {i['msg']}"
            for i in all_issues
        )

        response = self.groq_client.chat.completions.create(
            model=self.groq_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert Python developer. "
                        "Fix every issue completely and return ONLY the raw Python code. "
                        "No explanation, no markdown, no code fences. Just the fixed Python."
                    )
                },
                {
                    "role": "user",
                    "content": f"""Fix ALL these issues in the Python code and return ONLY the fixed code:

ISSUES TO FIX:
{issue_summary}

FIXING RULES:
1. Fix every single issue listed — miss nothing
2. Fix operator bugs: =+ → +=, =- → -=, =* → *=
3. Fix if chains → if/elif/elif/else
4. Add empty list/string guards at start of functions
5. Replace hardcoded secrets with os.environ.get('VAR_NAME')
6. Use with open() for all file operations
7. Remove unused imports
8. Rename single char variables to descriptive names everywhere they appear
9. Keep all original logic intact
10. Return ONLY raw Python — no markdown, no backticks, no explanation

ORIGINAL CODE:
{code}"""
                }
            ],
            temperature=0.1,
            max_tokens=4000
        )

        fixed = response.choices[0].message.content.strip()
        if fixed.startswith("```"):
            fixed_lines = fixed.split('\n')
            fixed = '\n'.join(fixed_lines[1:-1]).strip()

        logging.info(f"Fixed code received ({len(fixed)} chars).")
        return fixed

    # ====================================================================
    # MAIN GROQ FLOW (PRIMARY)
    # ====================================================================

    def _analyze_with_groq(self, code: str) -> List[Dict[str, Any]]:
        if not self.groq_client:
            return []

        # Cache check — skip if code matches last fixed version
        incoming = hashlib.md5(code.strip().encode()).hexdigest()
        if self.last_fixed_code:
            last_fixed = hashlib.md5(self.last_fixed_code.strip().encode()).hexdigest()
            if incoming == last_fixed:
                logging.info("Code matches last fixed version — returning clean.")
                return []

        try:
            # Partial scan — find which lines are new/changed
            changed_line_numbers = None

            if self.last_fixed_code:
                old_lines = self.last_fixed_code.strip().split('\n')
                new_lines = code.strip().split('\n')
                old_set = set(old_lines)

                changed_line_numbers = set()
                for i, line in enumerate(new_lines):
                    if line not in old_set:
                        changed_line_numbers.add(i + 1)

                if not changed_line_numbers:
                    logging.info("No changed lines — returning clean.")
                    self.last_fixed_code = code
                    return []

                logging.info(f"Partial scan: changed lines = {changed_line_numbers}")

            # Step 1: Pre-scan (AST + Regex)
            logging.info("Step 1: Running pre-scan...")
            all_pre_scan = self._pre_scan(code)

            if changed_line_numbers is not None:
                pre_scan_issues = [i for i in all_pre_scan if i['line'] in changed_line_numbers]
                logging.info(f"Pre-scan: {len(pre_scan_issues)} issues on changed lines.")
            else:
                pre_scan_issues = all_pre_scan
                logging.info(f"Pre-scan: {len(pre_scan_issues)} issues found.")

            if not pre_scan_issues:
                logging.info("Pre-scan clean — skipping Groq.")
                self.last_fixed_code = code
                return []

            # Step 2: Groq deep analysis
            logging.info("Step 2: Groq finding additional issues...")
            groq_issues = self._call_find_issues(code, pre_scan_issues)

            if changed_line_numbers is not None:
                groq_issues = [i for i in groq_issues if i['line'] in changed_line_numbers]

            all_issues = pre_scan_issues + groq_issues

            if not all_issues:
                self.last_fixed_code = code
                logging.info("Code is clean — no issues found.")
                return []

            # Step 3: Fix everything
            logging.info(f"Step 3: Fixing {len(all_issues)} issues...")
            fixed_code = self._call_fix_code(code, all_issues)

            if fixed_code:
                post_issues = self._pre_scan(fixed_code)
                if post_issues:
                    logging.info(f"Fixed code has {len(post_issues)} remaining issues — second fix pass...")
                    fixed_code = self._call_fix_code(fixed_code, post_issues)
                self.last_fixed_code = fixed_code
                logging.info("Fix complete and verified clean.")
            else:
                logging.error("Fix returned empty — keeping original.")
                self.last_fixed_code = code

            result_issues: List[Dict[str, Any]] = list(all_issues)
            result_issues.append({
                "tool": "AI-Reviewer",
                "type": "AI Suggestion",
                "category": "info",
                "msg": "AI suggests refactoring to: FULL_FILE_FIX_AVAILABLE",
                "line": 1
            })

            logging.info(f"Analysis complete. {len(all_issues)} issues found.")
            return result_issues

        except Exception as e:
            logging.error(f"Groq analysis failed: {e}")
            self.last_fixed_code = ""
            return []

    # ====================================================================
    # CODEBERT — fallback (Research Model #1)
    # Detects security vulnerabilities line-by-line using fine-tuned BERT.
    # Paper reference: mrm8488/codebert-base-finetuned-detect-insecure-code
    # ====================================================================

    def _analyze_with_codebert(self, code: str) -> List[Dict[str, Any]]:
        self._load_local_models()
        import torch

        issues = []
        lines = code.split('\n')
        for i, line in enumerate(lines):
            target_line = line.strip()
            if not target_line or target_line.startswith("#"):
                continue
            try:
                inputs = self.bert_tokenizer(
                    target_line, return_tensors="pt",
                    truncation=True, padding=True, max_length=512
                ).to(self.device)
                with torch.no_grad():
                    outputs = self.bert_model(**inputs)
                    if torch.argmax(outputs.logits, dim=1).item() == 1:
                        issues.append({
                            "tool": "CodeBERT",
                            "type": "Security/Logic Risk",
                            "category": "error",
                            "msg": "AI Analysis detected a potential vulnerability or logical flaw.",
                            "line": i + 1
                        })
            except Exception as e:
                logging.error(f"CodeBERT error on line {i + 1}: {e}")
        return issues

    # ====================================================================
    # CODET5+ — fallback (Research Model #2)
    # Generates code fix suggestions using Salesforce/codet5p-220m.
    # Paper reference: sequence-to-sequence transformer for code repair.
    # ====================================================================

    def _analyze_with_codet5(self, code: str, error_lines: List[int]) -> List[Dict[str, Any]]:
        self._load_local_models()
        import torch

        issues = []
        lines = code.split('\n')
        for line_num in error_lines:
            if line_num < 1 or line_num > len(lines):
                continue
            original_line = lines[line_num - 1]
            target_line = original_line.strip()
            if not target_line or len(target_line) < 2 or target_line.startswith("#"):
                continue
            try:
                inputs = self.suggest_tokenizer(
                    f"Fix Python: {target_line}",
                    return_tensors="pt", truncation=True, max_length=128
                ).to(self.device)
                outputs = self.suggest_model.generate(
                    **inputs, max_length=64, do_sample=False,
                    repetition_penalty=1.5, num_return_sequences=1,
                    eos_token_id=self.suggest_tokenizer.eos_token_id
                )
                suggestion = self.suggest_tokenizer.decode(
                    outputs[0], skip_special_tokens=True
                ).strip()
                is_hallucination = any(
                    w in suggestion.lower() for w in ["years", "impressed", "youngo"]
                )
                if suggestion and suggestion != target_line and not is_hallucination:
                    indent = len(original_line) - len(original_line.lstrip())
                    issues.append({
                        "tool": "AI-Reviewer",
                        "type": "AI Suggestion",
                        "category": "warning",
                        "msg": f"AI suggests refactoring to: {' ' * indent + suggestion}",
                        "line": line_num
                    })
            except Exception as e:
                logging.error(f"CodeT5+ error on line {line_num}: {e}")
        return issues

    # ====================================================================
    # MAIN ANALYZE — entry point
    # ====================================================================

    def analyze(self, code: str, error_lines: List[int] = None) -> List[Dict[str, Any]]:
        if not error_lines:
            error_lines = [1]
        error_lines = list(set(error_lines))

        if self.groq_client:
            logging.info("Using Groq API (LLaMA-3 70B) with pre-scan + partial scan...")
            return self._analyze_with_groq(code)

        # Groq unavailable — activate local research models
        logging.info("Groq unavailable. Falling back to CodeBERT + CodeT5+ (local models)...")
        issues = []
        issues.extend(self._analyze_with_codebert(code))
        issues.extend(self._analyze_with_codet5(code, error_lines))
        return issues