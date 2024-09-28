from datetime import datetime, timedelta

def calculate_sleep_time(start_time, end_time, total_records):
    """Calculate the sleep time between processing each record."""
    duration = (end_time - start_time).total_seconds()
    if duration <= 0:
        raise ValueError("End time must be after start time")
    
    # Assuming each request takes approximately 1 second
    request_duration = 1
    if total_records > 1:
        sleep_time = (duration - total_records * request_duration) / (total_records - 1)
    else:
        sleep_time = 0
    
    if sleep_time < 0:
        sleep_time = 0  # Ensure sleep time is non-negative
    
    return sleep_time

def main():
    # Input start and end times
    start_time_str = input("Enter start time (YYYY-MM-DD HH:MM:SS): ")
    end_time_str = input("Enter end time (YYYY-MM-DD HH:MM:SS): ")

    try:
        start_time = datetime.fromisoformat(start_time_str)
        end_time = datetime.fromisoformat(end_time_str)
    except ValueError:
        print("Invalid date format. Please use YYYY-MM-DD HH:MM:SS")
        return

    # Number of records to process
    total_records = 5

    try:
        sleep_time = calculate_sleep_time(start_time, end_time, total_records)
        print(f"Calculated sleep time between each record: {sleep_time:.2f} seconds")
    except ValueError as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
