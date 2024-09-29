import re
import requests

def fetch_variant_id(product_link):
    try:
        
        url = f'{product_link}.json'
        # print(f"Fetching data from: {url}")
        
        response = requests.get(url)
        
        if response.status_code == 200:
            data = response.json()
            # print("Data retrieved successfully.")
            variants = data.get('product', {}).get('variants', [])
            
            if variants:
                variant_id = variants[0].get('id')
                return(f"{variant_id}")
            else:
                print("Error: No variants found for the product.")
        else:
            print(f"Error: Failed to retrieve data, status code: {response.status_code}")
    
    except Exception as e:
        print(f"Error fetching variant ID: {e}")

def extract_store_url_from_link(product_link):
    match = re.search(r'https?://([^/]+)/', product_link)
    return match.group(1) if match else None



link = "https://3908a9-4f.myshopify.com/products/hrx-by-hrithik-roshan"

# store_url = extract_store_url_from_link(link)
# print(store_url)  # Output: 3908a9-4f.myshopify.com
# print(fetch_variant_id(link))
