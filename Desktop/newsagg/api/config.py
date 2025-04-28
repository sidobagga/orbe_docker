import os
from openai import OpenAI
from newsapi import NewsApiClient

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Initialize NewsAPI client
newsapi = NewsApiClient(api_key="9ca6418863754b0bbd6d047fc9d2be43") 