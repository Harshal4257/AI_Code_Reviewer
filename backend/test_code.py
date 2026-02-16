# In: test_code.py

import os  # Pylint Error: Unused import (W0611)

# Bandit Error: Hardcoded password (B105)
admin_pass = "password123" 

def my_function():
    x = 10
    y = 20  # Pylint Error: Unused variable 'y' (W0612)
    return x

def another_function():
    name = "Harsh"
    print(nme) # Pylint Error: Undefined variable 'nme' (E0602)