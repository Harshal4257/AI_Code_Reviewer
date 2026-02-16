import torch
from transformers import (
    AutoTokenizer, 
    AutoModelForSequenceClassification,
    AutoModelForSeq2SeqLM
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

        # 2. Refactoring Suggestions (CodeT5 + CodeBERTa Tokenizer)
        self.suggest_tokenizer_name = "huggingface/CodeBERTa-small-v1"
        self.suggest_model_name = "Salesforce/codet5-small"
        self.suggest_tokenizer = AutoTokenizer.from_pretrained(self.suggest_tokenizer_name)
        self.suggest_model = AutoModelForSeq2SeqLM.from_pretrained(self.suggest_model_name).to(self.device)

    def analyze(self, code: str) -> List[Dict[str, Any]]:
        issues = []
        
        # --- Task 1: Logic Bug Detection ---
        try:
            inputs = self.bert_tokenizer(code, return_tensors="pt", truncation=True, padding=True, max_length=512).to(self.device)
            with torch.no_grad():
                outputs = self.bert_model(**inputs)
                prediction = torch.argmax(outputs.logits, dim=1).item()
            
            if prediction == 1: 
                issues.append({
                    "tool": "CodeBERT",
                    "type": "Security/Logic Risk",
                    "msg": "AI Analysis detected a potential vulnerability or logical flaw.",
                    "line": 1
                })
        except Exception as e:
            logging.error(f"CodeBERT error: {e}")

        # --- Task 2: Advanced Suggestion Generation ---
        try:
            # We explicitly ask for a refactored version
            input_text = f"refactor: {code}"
            inputs = self.suggest_tokenizer(input_text, return_tensors="pt", truncation=True).to(self.device)
            
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

            if suggestion and len(suggestion) > 3 and suggestion.strip() != code.strip():
                issues.append({
                    "tool": "AI-Reviewer",
                    "type": "AI Suggestion",
                    "msg": f"AI suggests refactoring to: {suggestion}",
                    "line": 1
                })
        except Exception as e:
            logging.error(f"Suggestion generation error: {e}")

        return issues