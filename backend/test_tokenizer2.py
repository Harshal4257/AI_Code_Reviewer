from transformers import AutoTokenizer
import traceback

try:
    print("Testing AutoTokenizer(use_fast=False)...")
    t1 = AutoTokenizer.from_pretrained("Salesforce/codet5-small", use_fast=False)
    print("AutoTokenizer success!")
except Exception as e:
    print("AutoTokenizer failed:")
    traceback.print_exc()
