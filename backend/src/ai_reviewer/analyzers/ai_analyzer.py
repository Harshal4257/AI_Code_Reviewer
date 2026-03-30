import os
# --- STAGE 0: ENVIRONMENT FIXES ---
os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "true"
os.environ["HF_HUB_DISABLE_AUTO_CONVERSION"] = "1"

try:
    import transformers.safetensors_conversion as conversion
    conversion.auto_conversion = lambda *args, **kwargs: None
    print("Successfully blocked transformers auto-conversion thread.")
except ImportError:
    pass

import torch
import transformers
from transformers import (
    AutoTokenizer, 
    AutoModelForSequenceClassification,
    AutoModelForSeq2SeqLM,
    T5Tokenizer,      
    RobertaTokenizer
)
from typing import List, Dict, Any
from src.ai_reviewer.logger import logging

# Mute standard warnings
transformers.utils.logging.set_verbosity_error()

class AIAnalyzer:
    def __init__(self):
        logging.info("Initializing Finalized AI Architecture...")
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        # 1. Logic & Security (CodeBERT)
        self.bert_name = "mrm8488/codebert-base-finetuned-detect-insecure-code"
        self.bert_tokenizer = RobertaTokenizer.from_pretrained(self.bert_name, use_fast=False)
        self.bert_model = AutoModelForSequenceClassification.from_pretrained(
            self.bert_name,
            use_safetensors=False
        ).to(self.device)

        # 2. Refactoring Suggestions (CodeT5+)
        self.suggest_model_name = "Salesforce/codet5p-220m"
        try:
            self.suggest_tokenizer = T5Tokenizer.from_pretrained(self.suggest_model_name, use_fast=False)
        except Exception:
            self.suggest_tokenizer = T5Tokenizer.from_pretrained("t5-base", use_fast=False)
            
        self.suggest_model = AutoModelForSeq2SeqLM.from_pretrained(
            self.suggest_model_name,
            use_safetensors=False
        ).to(self.device)

    def analyze(self, code: str, error_lines: List[int] = None) -> List[Dict[str, Any]]:
        issues = []
        lines = code.split('\n')
        if not error_lines:
            error_lines = [1] 
        error_lines = list(set(error_lines))

        # --- Phase 1: CodeBERT Security Check ---
        for i, line in enumerate(lines):
            target_line = line.strip()
            if not target_line or target_line.startswith("#"):
                continue
            try:
                inputs = self.bert_tokenizer(target_line, return_tensors="pt", truncation=True, padding=True, max_length=512).to(self.device)
                with torch.no_grad():
                    outputs = self.bert_model(**inputs)
                    if torch.argmax(outputs.logits, dim=1).item() == 1: 
                        issues.append({
                            "tool": "CodeBERT",
                            "type": "Security/Logic Risk",
                            "msg": "AI Analysis detected a potential vulnerability or logical flaw.",
                            "line": i + 1 
                        })
            except Exception as e:
                logging.error(f"CodeBERT error on line {i + 1}: {e}")

        # --- Phase 2: CodeT5+ Refactoring Suggestions ---
        for line_num in error_lines:
            if line_num < 1 or line_num > len(lines): continue
            
            original_line_with_indent = lines[line_num - 1]
            target_line = original_line_with_indent.strip()
            
            # Skip empty lines, very short lines, or simple comments
            if not target_line or len(target_line) < 2 or target_line.startswith("#"): 
                continue

            try:
                # Prompt optimized for T5-style instruction following
                input_text = f"Fix Python: {target_line}"
                inputs = self.suggest_tokenizer(input_text, return_tensors="pt", truncation=True, max_length=128).to(self.device)
                
                # --- STABLE GENERATION PARAMS ---
                outputs = self.suggest_model.generate(
                    **inputs,
                    max_length=64,
                    do_sample=False,         # Greedy search for maximum stability
                    repetition_penalty=1.5,  # Stop repeating "years years years"
                    num_return_sequences=1,
                    eos_token_id=self.suggest_tokenizer.eos_token_id
                )
                
                suggestion = self.suggest_tokenizer.decode(outputs[0], skip_special_tokens=True).strip()
                
                # --- REFINED FILTER ---
                # Only filter if it contains clear hallucination keywords
                is_hallucination = any(word in suggestion.lower() for word in ["years", "impressed", "youngo"])
                
                if suggestion and suggestion != target_line and not is_hallucination:
                    indent_size = len(original_line_with_indent) - len(original_line_with_indent.lstrip())
                    issues.append({
                        "tool": "AI-Reviewer",
                        "type": "AI Suggestion",
                        "msg": f"AI suggests refactoring to: {' ' * indent_size + suggestion}",
                        "line": line_num
                    })
                else:
                    logging.info(f"AI suggestion for line {line_num} filtered: suggestion was '{suggestion}'")

            except Exception as e:
                logging.error(f"CodeT5 error on line {line_num}: {e}")
                
        return issues