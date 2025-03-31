from flask import Flask, render_template, request, jsonify
from groq import Groq
import sqlite3
import os
import requests
from bs4 import BeautifulSoup
import wikipedia
import re
from urllib.parse import urlparse

app = Flask(__name__)
app.secret_key = 'supersecretkey'

# Set your Groq API key
groq_api_key = "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"
groq_client = Groq(api_key=groq_api_key)

# Database setup
DATABASE_FILE = 'chat_sessions.db'

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

def replace_model_references(text):
    """Replace all references to Meta/LLaMA with Lorentzos"""
    return text.replace("Meta", "Lorentzos").replace("LLaMA", "Lorentzos")

def get_user_messages(user_token):
    with sqlite3.connect(DATABASE_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT role, content FROM conversations 
            WHERE user_token = ? 
            ORDER BY timestamp ASC
        ''', (user_token,))
        rows = cursor.fetchall()
        return [{"role": row[0], "content": row[1]} for row in rows]

def add_message(user_token, role, content):
    with sqlite3.connect(DATABASE_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO conversations (user_token, role, content)
            VALUES (?, ?, ?)
        ''', (user_token, role, content))
        conn.commit()

def clear_user_messages(user_token):
    with sqlite3.connect(DATABASE_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            DELETE FROM conversations WHERE user_token = ?
        ''', (user_token,))
        conn.commit()

def duckduckgo_search(query, max_results=3):
    """Free web search using DuckDuckGo"""
    try:
        url = "https://html.duckduckgo.com/html/"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; rv:91.0) Gecko/20100101 Firefox/91.0'
        }
        params = {'q': query, 'kl': 'us-en'}
        
        response = requests.post(url, data=params, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        results = []
        for result in soup.select('.result__body')[:max_results]:
            title = result.select_one('.result__title a').text
            link = result.select_one('.result__url')['href']
            snippet = result.select_one('.result__snippet').text if result.select_one('.result__snippet') else ""
            
            if link.startswith('//'):
                link = 'https:' + link
            
            results.append({
                'title': title,
                'link': link,
                'snippet': snippet
            })
        return results
    except Exception as e:
        print(f"DuckDuckGo search error: {e}")
        return []

def wikipedia_search(query, max_results=3):
    """Search Wikipedia for information"""
    try:
        wikipedia.set_lang("en")
        search_results = wikipedia.search(query, results=max_results)
        results = []
        
        for title in search_results:
            try:
                page = wikipedia.page(title, auto_suggest=False)
                results.append({
                    'title': page.title,
                    'link': page.url,
                    'snippet': wikipedia.summary(title, sentences=2)
                })
            except:
                continue
                
        return results
    except Exception as e:
        print(f"Wikipedia search error: {e}")
        return []

def perform_web_search(query):
    """Combine multiple free search methods"""
    results = []
    
    ddg_results = duckduckgo_search(query)
    if ddg_results:
        results.extend(ddg_results)
    
    wiki_results = wikipedia_search(query, max_results=(3 - len(results)))
    if wiki_results:
        results.extend(wiki_results)
    
    return results[:3]

def is_valid_url(url):
    """Check if a URL is valid and safe to scrape"""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False

def scrape_website(url):
    """Scrape the content of a specific website"""
    try:
        if not is_valid_url(url):
            return None
            
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Remove unwanted elements
        for element in soup(['script', 'style', 'nav', 'footer', 'iframe', 'noscript', 'img', 'svg']):
            element.decompose()
        
        # Get clean text content
        text = soup.get_text(separator='\n', strip=True)
        
        # Clean up excessive whitespace
        text = re.sub(r'\n\s*\n', '\n\n', text)
        
        # Get page title
        title = soup.title.string if soup.title else "No title found"
        
        # Get meta description if available
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        description = meta_desc['content'] if meta_desc else ""
        
        # Get main headings
        headings = []
        for heading in soup.find_all(['h1', 'h2', 'h3']):
            headings.append(f"{heading.name.upper()}: {heading.get_text(strip=True)}")
        
        return {
            'title': title,
            'description': description,
            'headings': '\n'.join(headings[:5]),  # First 5 headings
            'content': text[:10000]  # First 10,000 chars
        }
    except Exception as e:
        print(f"Website scraping error: {e}")
        return None

@app.route('/')
def index():
    if not os.path.exists(DATABASE_FILE):
        init_db()
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    user_token = request.json.get('userToken')
    user_message = request.json['message']
    use_web_search = request.json.get('webSearch', False)

    # Check if message contains a URL to scrape
    url_pattern = r'https?://[^\s]+'
    urls = re.findall(url_pattern, user_message)
    scraped_content = ""
    
    if urls:
        for url in urls[:1]:  # Limit to first URL
            result = scrape_website(url)
            if result:
                scraped_content = f"""
Scraped content from {url}:
Title: {result['title']}
Description: {result['description']}
Main Headings:
{result['headings']}

Content Excerpt:
{result['content'][:2000]}... [truncated]
"""

    # Add user message to database
    add_message(user_token, "user", user_message)

    # Get conversation history from database
    conversation_history = get_user_messages(user_token)

    # Perform web search if enabled (only if no specific URL was provided)
    search_context = ""
    if use_web_search and not urls:
        search_results = perform_web_search(user_message)
        if search_results:
            search_context = "\nWeb Search Results:\n"
            for i, result in enumerate(search_results, 1):
                search_context += f"{i}. {result['title']}\n{result['snippet']}\nSource: {result['link']}\n\n"
    
    system_message = {
        "role": "system",
        "content": f"""You are Lorentzos AI. Analyze and respond to the user's query.
{scraped_content if scraped_content else ''}
{search_context if search_context else ''}
When summarizing websites, focus on the key information and main purpose of the site."""
    }
    
    messages = [system_message] + conversation_history

    completion = groq_client.chat.completions.create(
        model="llama3-8b-8192",
        messages=messages,
        temperature=0.7,  # Slightly lower for more focused responses
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

    return jsonify(reply=modified_response)

@app.route('/new_chat', methods=['POST'])
def new_chat():
    user_token = request.json.get('userToken')
    clear_user_messages(user_token)
    return jsonify(success=True)

if __name__ == '__main__':
    init_db()
    app.run(debug=True)