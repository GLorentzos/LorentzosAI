from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from groq import Groq
import sqlite3
import os
import requests
from bs4 import BeautifulSoup
import wikipedia
import re
from urllib.parse import urlparse
from jinja2 import Environment, FileSystemLoader
from fastapi.templating import Jinja2Templates
app = FastAPI()

# Set your Groq API key
groq_api_key = "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"
groq_client = Groq(api_key=groq_api_key)

DATABASE_FILE = "chat_sessions.db"

# Database initialization
def init_db():
    with sqlite3.connect(DATABASE_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_token TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()

init_db()

class ChatRequest(BaseModel):
    userToken: str
    message: str
    webSearch: bool = False


@app.post("/chat")
def chat(request: ChatRequest):
    user_token = request.userToken
    user_message = request.message
    use_web_search = request.webSearch
    
    add_message(user_token, "user", user_message)
    conversation_history = get_user_messages(user_token)

    system_message = {
        "role": "system",
        "content": "You are Lorentzos AI. Analyze and respond to the user's query."
    }
    
    messages = [system_message] + conversation_history
    
    completion = groq_client.chat.completions.create(
        model="llama3-8b-8192",
        messages=messages,
        temperature=0.7,
        max_tokens=1500,
        top_p=1,
        stream=True,
        stop=None,
    )
    
    response = ""
    for chunk in completion:
        response += chunk.choices[0].delta.content or ""
    
    modified_response = replace_model_references(response)
    add_message(user_token, "assistant", modified_response)
    
    return JSONResponse(content={"reply": modified_response})

@app.post("/new_chat")
def new_chat(request: ChatRequest):
    clear_user_messages(request.userToken)
    return JSONResponse(content={"success": True})

# Set up Jinja2 environment
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
    
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
