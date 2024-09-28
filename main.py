from flask import Flask, request, jsonify, render_template, redirect, url_for
import csv
import requests
import os
from werkzeug.utils import secure_filename
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
from threading import Lock
import uuid
from logging import StreamHandler
from flask import send_from_directory
from datetime import datetime


app = Flask(__name__)

# Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'csv'}
MAX_THREADS = 1

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s %(threadName)s : %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        StreamHandler()  # This sends logs to the console
    ]
)

# Load sensitive information from environment variables
SHOPIFY_API_KEY = "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"
SHOPIFY_STORE_URL = "3908a9-4f.myshopify.com"
SHOPIFY_VARIANT_ID = "46067649904854"

headers = {
    'X-Shopify-Access-Token': SHOPIFY_API_KEY,
    'Content-Type': 'application/json',
}

# In-memory storage for background task statuses
tasks = {}
task_lock = Lock()

def load_csv_data(csv_file_path):
    """Read and process the CSV file."""
    processed_data = []
    try:
        with open(csv_file_path, mode='r', newline='', encoding='utf-8') as csvfile:
            csv_reader = csv.DictReader(csvfile)
            for row in csv_reader:
                data = {
                    'name': row.get('Shipping Name', '').strip() or row.get('Biling Name', '').strip(),
                    'address1': row.get('Shipping Address1', '').strip() or row.get('Billing Address1', '').strip(),
                    'address2': row.get('Shipping Address2', '').strip() or row.get('Billing Address2', '').strip(),
                    'pincode': row.get('Shipping Zip', '').strip() or row.get('Billing Zip', '').strip(),
                    'city': row.get('Shipping City', '').strip() or row.get('Billing City', '').strip(),
                    'state': row.get('Shipping Province', '').strip() or row.get('Billing Province', '').strip(),
                    'phone_number': row.get('Shipping Phone', '').strip() or row.get('Billing Phone', '').strip(),
                    'product_id': row.get('Lineitem sku', '').strip(),
                    'quantity': row.get('Lineitem quantity', '').strip()
                }
                processed_data.append(data)
        logging.info(f"Loaded {len(processed_data)} records from {csv_file_path}")
    except Exception as e:
        logging.error(f"Error loading CSV data: {e}")
        raise
    return processed_data

def split_name(full_name):
    """Split full name into first name and last name."""
    parts = full_name.split()
    firstname = parts[0]
    lastname = " ".join(parts[1:]) if len(parts) > 1 else ""
    return firstname, lastname

def format_phone_number(phone_number):
    """Validate and format phone number."""
    phone_number = phone_number.replace(" ", "").replace("-", "")
    if len(phone_number) == 10 and phone_number.isdigit():
        return phone_number
    elif phone_number.startswith("+91"):
        phone_number = phone_number.replace("+91", "")
        while len(phone_number) > 10 and phone_number.startswith("91"):
            phone_number = phone_number[2:]
        if len(phone_number) == 10 and phone_number.isdigit():
            return phone_number
    logging.warning(f"Invalid phone number format: {phone_number}")
    return None

def process_order(entry, variant_id, store_url, task_id):
    """Process each order and send data to Shopify."""
    try:
        firstname, lastname = split_name(entry['name'])
        phone = format_phone_number(entry['phone_number'])
        if not phone:
            logging.warning(f"Skipping order due to invalid phone number: {entry['phone_number']}")
            with task_lock:
                tasks[task_id]['skipped_orders'].append(entry)
            return {'status': 'skipped', 'reason': 'Invalid phone number'}

        json_data = {
            'order': {
                'line_items': [
                    {
                        'variant_id': variant_id,
                        'quantity': int(entry['quantity']),
                    },
                ],
                'customer': {
                    'first_name': firstname,
                    'last_name': lastname,
                },
                'shipping_address': {
                    'first_name': firstname,
                    'last_name': lastname,
                    'address1': entry['address1'],
                    'address2': entry['address2'],
                    'phone': phone,
                    'city': entry['city'],
                    'province': entry['state'],
                    'country': 'IN',
                    'zip': entry['pincode'],
                },
                'financial_status': 'pending',
            },
        }

        response = requests.post(
            f'https://{store_url}/admin/api/2024-01/orders.json',
            headers=headers,
            json=json_data,
            timeout=10
        )

        if response.status_code == 201:
            order_id = response.json().get('order', {}).get('id')
            logging.info(f"Order created successfully: {order_id}")
            if order_id:
                # Create Payment Terms
                graphql_query = '''
                mutation PaymentTermsCreate($referenceId: ID!, $paymentTermsAttributes: PaymentTermsCreateInput!) {
                    paymentTermsCreate(referenceId: $referenceId, paymentTermsAttributes: $paymentTermsAttributes) {
                        paymentTerms {
                            id
                        }
                        userErrors {
                            field
                            message
                        }
                    }
                }
                '''
                variables = {
                    'referenceId': f'gid://shopify/Order/{order_id}',
                    'paymentTermsAttributes': {
                        'paymentTermsTemplateId': 'gid://shopify/PaymentTermsTemplate/1',
                    },
                }
                graphql_data = {
                    'query': graphql_query,
                    'variables': variables,
                }

                graphql_response = requests.post(
                    f'https://{store_url}/admin/api/unstable/graphql.json',
                    headers=headers,
                    json=graphql_data,
                    timeout=10
                )

                if graphql_response.status_code == 200:
                    logging.info(f"Payment terms created for order {order_id}")
                else:
                    logging.error(f"Failed to create payment terms for order {order_id}: {graphql_response.text}")
            return {'status': 'success', 'order_id': order_id}
        else:
            logging.error(f"Failed to create order: {response.status_code} - {response.text}")
            with task_lock:
                tasks[task_id]['skipped_orders'].append(entry)
            return {'status': 'failed', 'reason': response.text}
    except Exception as e:
        logging.error(f"Exception in processing order: {e}")
        with task_lock:
            tasks[task_id]['skipped_orders'].append(entry)
        return {'status': 'error', 'reason': str(e)}

def allowed_file(filename):
    """Check if the file has an allowed extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_failed_orders(task_id, failed_orders):
    """Save failed orders to a file with the task ID."""
    filename = f"failed_orders_{task_id}.csv"
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    with open(file_path, mode='w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['name', 'address1', 'address2', 'pincode', 'city', 'state', 'phone_number', 'product_id', 'quantity', 'error_reason']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for order in failed_orders:
            writer.writerow(order)

def run_threads(processed_data, variant_id, store_url, task_id, max_threads=MAX_THREADS):
    """Process orders using a thread pool."""
    failed_orders = []
    task = tasks[task_id]
    sleep_time = task.get('sleep_time', 0)
    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        future_to_order = {executor.submit(process_order_with_sleep, entry, variant_id, store_url, task_id, sleep_time): entry for entry in processed_data}
        for future in as_completed(future_to_order):
            entry = future_to_order[future]
            try:
                result = future.result()
                with task_lock:
                    tasks[task_id]['results'].append(result)
                    if result['status'] != 'success':
                        failed_order = {**entry, 'error_reason': result.get('reason', 'Unknown error')}
                        failed_orders.append(failed_order)

            except Exception as exc:
                logging.error(f"Order processing generated an exception: {exc}")
                with task_lock:
                    tasks[task_id]['results'].append({'status': 'error', 'reason': str(exc)})
                failed_order = {**entry, 'error_reason': str(exc)}
                failed_orders.append(failed_order)

    # Update task status to 'Completed' once done
    with task_lock:
        tasks[task_id]['status'] = 'Completed'
        save_failed_orders(task_id, failed_orders)

# def process_order_with_sleep(entry, variant_id, store_url, task_id, sleep_time):
#     """Process each order with a delay between requests."""
#     import time
#     try:
#         time.sleep(sleep_time)  # Apply sleep time between requests
#         return process_order(entry, variant_id, store_url, task_id)
#     except Exception as e:
#         logging.error(f"Exception in processing order: {e}")
#         return {'status': 'error', 'reason': str(e)}


def process_order_with_sleep(entry, variant_id, store_url, task_id, sleep_time):
    """Process each order with a delay between requests and check for cancellation."""
    import time
    try:
        time.sleep(sleep_time)  # Apply sleep time between requests

        with task_lock:
            if tasks[task_id].get('cancelled', False):
                logging.info(f"Task {task_id} has been canceled. Skipping order.")
                return {'status': 'cancelled'}

        return process_order(entry, variant_id, store_url, task_id)
    except Exception as e:
        logging.error(f"Exception in processing order: {e}")
        return {'status': 'error', 'reason': str(e)}


@app.route('/cancel_task/<task_id>', methods=['GET'])
def cancel_task(task_id):
    """Cancel a running task."""
    with task_lock:
        task = tasks.get(task_id)
        if not task:
            return jsonify({'error': 'Task not found'}), 404

        if task['status'] == 'Completed':
            return jsonify({'error': 'Task already completed'}), 400

        task['cancelled'] = True
        task['status'] = 'Cancelled'
        logging.info(f"Task {task_id} has been cancelled.")
        return jsonify({'message': f"Task {task_id} has been cancelled"}), 200



def calculate_sleep_time(start_time, end_time, num_requests):
    """Calculate the required sleep time between requests."""
    total_time_available = (end_time - start_time).total_seconds()
    request_time = 1  # Each request takes 1 second
    total_request_time = num_requests * request_time

    total_sleep_time = total_time_available - total_request_time

    if total_sleep_time < 0:
        raise ValueError("Not enough time available to complete all requests")

    sleep_time_between_requests = total_sleep_time / (num_requests - 1) if num_requests > 1 else 0
    return sleep_time_between_requests


@app.route('/process_orders', methods=['POST'])
def process_orders():
    """Handle CSV file upload and process orders in the background."""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file part in the request'}), 400

        csv_file = request.files['file']
        if csv_file.filename == '':
            return jsonify({'error': 'No file selected for uploading'}), 400

        if not allowed_file(csv_file.filename):
            return jsonify({'error': 'Invalid file type. Only CSV files are allowed.'}), 400

        filename = secure_filename(csv_file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        csv_file.save(file_path)
        logging.info(f"File saved to {file_path}")

        variant_id = request.form.get('variant_id', SHOPIFY_VARIANT_ID)
        if not variant_id:
            return jsonify({'error': 'Variant ID not provided'}), 400

        store_url = request.form.get('store_url') or SHOPIFY_STORE_URL
        store_api = request.form.get('store_api') or SHOPIFY_API_KEY

        end_time_str = request.form.get('end_time')

        try:
            start_time = datetime.now()
            if not end_time_str:
                end_time = datetime.now()
            else:
                end_time = datetime.fromisoformat(end_time_str) or datetime.now()
        except ValueError:
            return jsonify({'error': 'Invalid date format'}), 400

        processed_data = load_csv_data(file_path)
        if not processed_data:
            return jsonify({'error': 'No data found in CSV file'}), 400

        # Calculate the duration
        total_requests = len(processed_data)
        total_duration = (end_time - start_time).total_seconds()
        if total_duration <= 0:
            return jsonify({'error': 'End time must be after start time'}), 400
        
        request_duration = 1  # Assuming each request takes approximately 1 second
        if total_requests > 1:
            sleep_time = (total_duration - total_requests * request_duration) / (total_requests - 1)
            print(f"sleep time : {sleep_time}")
        else:
            sleep_time = 0

        if sleep_time < 0:
            sleep_time = 0  # Ensure sleep time is non-negative

        task_id = str(uuid.uuid4())
        with task_lock:
            tasks[task_id] = {
                'status': 'Running',
                'results': [],
                'skipped_orders': [],
                'start_time': start_time,
                'end_time': end_time_str,
                'sleep_time': sleep_time
            }

        executor = ThreadPoolExecutor(max_workers=1)
        executor.submit(run_threads, processed_data, variant_id, store_url, task_id, max_threads=1)
        return jsonify({'task_id': task_id, 'message': 'Order processing started'}), 202

    except Exception as e:
        logging.error(f"Error in process_orders: {e}")
        return jsonify({'error': str(e)}), 500



@app.route('/task_status/<task_id>', methods=['GET'])
def task_status(task_id):
    """Get the status and results of a background task."""
    task = tasks.get(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    return jsonify(task), 200

@app.route('/status/<task_id>', methods=['GET'])
def task_statu(task_id):
    """Get the status and logs of the background task."""
    with task_lock:
        if task_id not in tasks:
            return jsonify({'error': 'Invalid task ID'}), 404

        task_info = tasks[task_id]
        return jsonify({
            'status': task_info['status'],
            'results': task_info['results'],
            'skipped_orders': task_info['skipped_orders']
        })


@app.route('/download_logs/<task_id>', methods=['GET'])
def download_logs(task_id):
    try:
        return send_from_directory(directory='uploads', path=f'failed_orders_{task_id}.csv', as_attachment=True)
    except FileNotFoundError:
        return jsonify({'status': 'error', 'message': 'File not found'}), 404


@app.route('/')
def index():
    """Render the main upload form page and display running tasks."""
    running_tasks = {task_id: task for task_id, task in tasks.items() if task['status'] == 'Running'}
    completed_tasks = {task_id: task for task_id, task in tasks.items() if task['status'] == 'Completed'}
    return render_template('index.html', running_tasks=running_tasks, completed_tasks=completed_tasks)


if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=8000)
