from dotenv import load_dotenv
import os
load_dotenv()

from groq import Groq

key = os.environ.get('GROQ_API_KEY')
print('Key found:', bool(key))

client = Groq(api_key=key)
response = client.chat.completions.create(
    model='llama-3.3-70b-versatile',
    messages=[{'role': 'user', 'content': 'say hello'}]
)
print('Groq response:', response.choices[0].message.content)