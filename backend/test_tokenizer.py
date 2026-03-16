from transformers import AutoTokenizer, RobertaTokenizer
import sys
import traceback

try:
    print("Testing AutoTokenizer...")
    t1 = AutoTokenizer.from_pretrained("Salesforce/codet5-small")
    print("AutoTokenizer success!")
except Exception as e:
    print("AutoTokenizer failed:")
    traceback.print_exc()

try:
    print("Testing RobertaTokenizer...")
    t2 = RobertaTokenizer.from_pretrained("Salesforce/codet5-small")
    print("RobertaTokenizer success!")
except Exception as e:
    print("RobertaTokenizer failed:")
    traceback.print_exc()
