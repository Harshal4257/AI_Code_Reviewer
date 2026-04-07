from google import genai

client = genai.Client(api_key="AIzaSyAuKjYBUbNsnn-zc4S7-x1qfzha6hmByec")
response = client.models.generate_content(
    model='gemini-2.0-flash-lite',
    contents='say hello'
)
print(response.text)