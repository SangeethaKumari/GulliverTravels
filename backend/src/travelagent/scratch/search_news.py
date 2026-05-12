import os
import requests
from dotenv import load_dotenv
load_dotenv()

SERPER_API_KEY = os.getenv("SERPER_API_KEY")


def fetch_serper_news(query: str) -> str:
    """Search Google using Serper API and return formatted search results."""
    print(f"Fetching news for query: {query}")
    url = "https://google.serper.dev/search"
    headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
    params = {"q": query, "num" : 8}
    
    response = requests.post(url, json=params, headers=headers)
    print(f"Fetching Response: {response}")
    
    if response.status_code == 200:
        results = response.json()
        organic_results = results.get("organic", [])
        
        if not organic_results:
            return f"No search results found for '{query}'."

        print(f"organic_results: {organic_results}")
        
        # Format the results as a string
        formatted_results = [f"**Serper Search Results for '{query}':**\n"]
        print(f"Formatted_results: {formatted_results}")
        
        for i, result in enumerate(organic_results[:8], 1):
            title = result.get("title", "No title")
            link = result.get("link", "No link")
            snippet = result.get("snippet", "No description")
            date = result.get("date", "")
            
            formatted_results.append(
                f"{i}. **Title:** {title}\n"
                f"   **URL:** {link}\n"
                f"   **Summary:** {snippet}\n"
                f"   **Date:** {date}\n"
            )
        print(f"Formatted_results: {formatted_results}")
        return "\n".join(formatted_results)
    else:
        return f"Error: {response.status_code}, {response.text}"




#print(fetch_serper_news("Trump"))
#print(os.getenv("SERPER_API_KEY"))