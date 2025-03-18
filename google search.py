#WORKING CODE
from botasaurus.browser import browser, Driver, AsyncQueueResult
from botasaurus.request import request, Request
import json
import re
import pandas as pd
import urllib.parse  

def extract_phone_number(huge_string):
    """Extracts a 10-digit phone number from 'tel:+1XXXXXXXXXX' format."""
    match = re.search(r'tel:\+1(\d{10})', huge_string)
    return match.group(1) if match else None

def extract_place_info(html):
    """
    Extracts title, address, phone, website, and reviews from the embedded JSON.
    
    Returns:
        dict: {"title": str, "address": str, "phone": str, "website": str, "reviews": float}
    """
    try:
        state_str = html.split(";window.APP_INITIALIZATION_STATE=")[1].split(";window.APP_FLAGS")[0]
        data = json.loads(state_str)

        # Extract Title & Address
        title_add = data[-3][0] if len(data) > 3 and isinstance(data[-3], list) else None
        if title_add:
            parts = title_add.split(" · ")
            title = parts[0].strip() if len(parts) > 0 else None
            address = parts[1].strip() if len(parts) > 1 else None
        else:
            title, address = None, None
        
        # Extract Reviews
        reviews_cat = data[-3][1] if len(data) > 3 else None
        parts = reviews_cat.split(" · ")
        reviews = parts[0].strip() if len(parts) > 0 else None
        category = parts[1].strip() if len(parts) > 1 else None
        

        # Extract Phone Number
        phone_input = str(data[3][6]) if len(data) > 3 and len(data[3]) > 6 else ""
        phone_number = extract_phone_number(phone_input)
        
        # Extract Website
        website = data[3][12][1] if len(data) > 3 and len(data[3]) > 12 and len(data[3][12]) > 1 else None
        

        return {"title": title, "address": address, "phone": phone_number, "website": website, "reviews":reviews, "category":category}
    
    except (IndexError, KeyError, TypeError, json.JSONDecodeError) as e:
        print("Error extracting place info:", e)
        return {"title": None, "address": None, "phone": None, "website": None, "reviews": None, "category": None}

@request(parallel=5, async_queue=True, max_retry=5)
def scrape_place_info(request: Request, link, metadata):
    """Scrapes title, address, phone, website and rating from a place's webpage."""
    cookies = metadata["cookies"]
    html = request.get(link, cookies=cookies, timeout=12).text
    info = extract_place_info(html)
    print("Scraped:", info)
    return info

def extract_links(driver):
    """Extracts valid place links from the feed."""
    links = driver.get_all_links('[role="feed"] > div > div > a')
    return [link for link in links if link.startswith("https://")]

def has_reached_end(driver):
    """Checks if the scrolling has reached the end of the feed."""
    return driver.select('p.fontBodyMedium > span > span') is not None

def format_google_maps_url(query):
    """Formats the search query into a Google Maps search URL."""
    encoded_query = urllib.parse.quote_plus(query)  
    return f"https://www.google.com/maps/search/{encoded_query}"

@browser()
def scrape_google_maps(driver: Driver, query):
    search_url = format_google_maps_url(query)
    print(f"Searching: {search_url}")

    driver.google_get(search_url, accept_google_cookies=True)
    
    scrape_place_obj: AsyncQueueResult = scrape_place_info()
    cookies = driver.get_cookies_dict()

    last_links = set()
    
    while True:
        links = set(extract_links(driver))
        new_links = links - last_links

        if not new_links:
            break
        
        scrape_place_obj.put(list(new_links), metadata={"cookies": cookies})
        last_links.update(new_links)

        print("Scrolling...")
        driver.scroll_to_bottom('[role="feed"]')
        
        if has_reached_end(driver):
            break

    results = scrape_place_obj.get()


    return results if results else []


user_query = input("Enter search query (e.g., 'coffee shops near New York'): ")
results = scrape_google_maps(user_query)
df = pd.DataFrame(results)
pretty_json = df.to_json(indent=4, orient="records")