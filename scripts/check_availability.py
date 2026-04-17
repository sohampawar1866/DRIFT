from pystac_client import Client
import datetime

def check_indian_coastline():
    api_url = "https://earth-search.aws.element84.com/v1"
    client = Client.open(api_url)
    
    locations = {
        "Mumbai (West Coast)": [72.7, 18.8, 73.0, 19.1],
        "Chennai (East Coast)": [80.2, 12.9, 80.5, 13.2],
        "Kochi (South West)": [76.1, 9.8, 76.4, 10.1],
        "Andaman Islands": [92.6, 11.5, 92.9, 11.8],
        "Lakshadweep": [72.6, 10.5, 72.9, 10.8]
    }
    
    # Check for imagery in the last 30 days
    end_date = datetime.datetime.now(datetime.timezone.utc)
    start_date = end_date - datetime.timedelta(days=30)
    date_range = f"{start_date.strftime('%Y-%m-%d')}/{end_date.strftime('%Y-%m-%d')}"
    
    print(f"Checking Sentinel-2 L2A availability for the last 30 days ({date_range})...\n")
    
    for name, bbox in locations.items():
        search = client.search(
            collections=["sentinel-2-l2a"],
            bbox=bbox,
            datetime=date_range,
            max_items=5
        )
        items = list(search.items())
        count = len(items)
        print(f"LOC: {name}: {count} images found.")
        if count > 0:
            best = items[0]
            print(f"   - Newest ID: {best.id}")
            print(f"   - Date: {best.datetime.strftime('%Y-%m-%d')}")
            print(f"   - Cloud Cover: {best.properties.get('eo:cloud_cover'):.1f}%")
        print("-" * 40)

if __name__ == "__main__":
    check_indian_coastline()
