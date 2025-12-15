import os
import google.generativeai as genai

print("Key present:", bool(os.getenv("GEMINI_API_KEY")))
print("Model:", os.getenv("GEMINI_MODEL"))

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

model = genai.GenerativeModel(os.getenv("GEMINI_MODEL"))
response = model.generate_content("Reply with exactly: OK")

print("Raw response:", response)
print("Text:", response.text)

