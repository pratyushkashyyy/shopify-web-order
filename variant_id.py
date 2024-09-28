import re
import requests

def fetch_variant_id(product_link):
    try:
        product_handle = extract_product_handle_from_link(product_link)
        if not product_handle:
            print("Error: Could not extract product handle from the link.")
            return

        url = f'https://solkart.in/products/{product_handle}.json'
        print(f"Fetching data from: {url}")
        
        response = requests.get(url)
        
        if response.status_code == 200:
            data = response.json()
            print("Data retrieved successfully.")
            variants = data.get('product', {}).get('variants', [])
            
            if variants:
                variant_id = variants[0].get('id')
                print(f"Fetched Variant ID: {variant_id}")
            else:
                print("Error: No variants found for the product.")
        else:
            print(f"Error: Failed to retrieve data, status code: {response.status_code}")
    
    except Exception as e:
        print(f"Error fetching variant ID: {e}")

def extract_product_handle_from_link(product_link):
    match = re.search(r'/products/([^/?]+)', product_link)
    return match.group(1) if match else None

link = "https://solkart.in/products/automatic-plants-water-system-with-adjustable-control-valve-switch"

fetch_variant_id(link)
