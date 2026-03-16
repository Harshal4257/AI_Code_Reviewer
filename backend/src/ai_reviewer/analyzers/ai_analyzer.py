import torch
from transformers import (
    AutoTokenizer, 
    AutoModelForSequenceClassification,
    AutoModelForSeq2SeqLM,
    RobertaTokenizer
)
from typing import List, Dict, Any
from src.ai_reviewer.logger import logging

class AIAnalyzer:
    def __init__(self):
        logging.info("Initializing Finalized AI Architecture...")
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        # 1. Logic & Security (CodeBERT)
        self.bert_name = "mrm8488/codebert-base-finetuned-detect-insecure-code"
        self.bert_tokenizer = AutoTokenizer.from_pretrained(self.bert_name)
        self.bert_model = AutoModelForSequenceClassification.from_pretrained(self.bert_name).to(self.device)

        # 2. Refactoring Suggestions (CodeT5 + CodeT5 Tokenizer)
        self.suggest_model_name = "Salesforce/codet5-small"
        self.suggest_tokenizer = RobertaTokenizer.from_pretrained(self.suggest_model_name)
        self.suggest_model = AutoModelForSeq2SeqLM.from_pretrained(self.suggest_model_name).to(self.device)

    def analyze(self, code: str, error_lines: List[int] = None) -> List[Dict[str, Any]]:
        issues = []
        lines = code.split('\n')
        
        # If no error lines provided, we at least scan line 1 
        if not error_lines:
            error_lines = []
        
        # De-duplicate
        error_lines = list(set(error_lines))

        # --- Task 1: Logic Bug Detection (CodeBERT) ---
        # Scan blocks of 10 lines at a time
        chunk_size = 10
        for i in range(0, len(lines), chunk_size):
            chunk = '\n'.join(lines[i:i+chunk_size])
            if not chunk.strip():
                continue
            try:
                inputs = self.bert_tokenizer(chunk, return_tensors="pt", truncation=True, padding=True, max_length=512).to(self.device)
                with torch.no_grad():
                    outputs = self.bert_model(**inputs)
                    prediction = torch.argmax(outputs.logits, dim=1).item()
                
                # If prediction is 1 (Insecure)
                if prediction == 1: 
                    issues.append({
                        "tool": "CodeBERT",
                        "type": "Security/Logic Risk",
                        "msg": "AI Analysis detected a potential vulnerability or logical flaw.",
                        "line": i + 1  # 1-indexed
                    })
            except Exception as e:
                logging.error(f"CodeBERT error: {e}")

        # --- Task 2: Advanced Suggestion Generation (CodeT5) on Error Lines ---
        for line_num in error_lines:
            # line_num is 1-indexed
            if line_num < 1 or line_num > len(lines):
                continue
            
            # Extract a small window (e.g., just the line)
            target_line = lines[line_num - 1].strip()
            if not target_line or len(target_line) < 3:
                continue

            try:
                # We ask for a refactored version
                input_text = f"fix bug: {target_line}"
                inputs = self.suggest_tokenizer(input_text, return_tensors="pt", truncation=True, max_length=128).to(self.device)
                
                # Use top-p and top-k sampling for more human-like suggestions
                outputs = self.suggest_model.generate(
                    **inputs, 
                    max_length=128,
                    do_sample=True,      # Enables more creative/descriptive output
                    top_p=0.95,          # Nucleus sampling
                    top_k=50,
                    temperature=0.7,     # Balances randomness and accuracy
                    num_return_sequences=1
                )
                suggestion = self.suggest_tokenizer.decode(outputs[0], skip_special_tokens=True)

                if suggestion and suggestion.strip() and suggestion.strip() != target_line:
                    # Provide original line indentation
                    indent = len(lines[line_num - 1]) - len(lines[line_num - 1].lstrip())
                    indented_suggestion = (" " * indent) + suggestion.strip()

                    issues.append({
                        "tool": "AI-Reviewer",
                        "type": "AI Suggestion",
                        "msg": f"AI suggests refactoring to: {indented_suggestion}",
                        "line": line_num
                    })
            except Exception as e:
                logging.error(f"CodeT5 generation error: {e}")

        return issues