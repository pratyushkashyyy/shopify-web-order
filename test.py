import csv

with open(r"/home/pk/Downloads/3423 Shampoo.csv", mode='r', newline='', encoding='utf-8') as csvfile:
            csv_reader = csv.DictReader(csvfile)
            for row in csv_reader:
                data = {
                    'name': row.get('Shipping Name').strip() or row.get('Billing Name','').strip(),
                    'address1': row.get('Shipping Address1').strip() or row.get('Billing Address1', '').strip(),
                    'address2': row.get('Shipping Address2').strip() or row.get('Billing Address2', '').strip(),
                    'pincode': row.get('Shipping Zip').strip() or row.get('Billing Zip', '').strip(),
                    'city': row.get('Shipping City').strip() or row.get('Billing City', '').strip(),
                    'state': row.get('Shipping Province').strip() or row.get('Billing Province', '').strip(),
                    'phone_number': row.get('Shipping Phone').strip() or row.get('Billing Phone', '').strip(),
                    'product_id': row.get('Lineitem sku').strip(),
                    'quantity': row.get('Lineitem quantity').strip()
                }
                if "9890599540" in data['phone_number']:
                    print(data)