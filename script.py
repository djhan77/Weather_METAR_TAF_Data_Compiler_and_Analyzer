import csv
import requests
import asyncio
import aiohttp
import json
import calendar
import os
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pyairports.airports import Airports
from math import radians, sin, cos, sqrt, asin
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("API_KEY") 

top_50_airports_icao = [
    "KATL",  # Atlanta
    "KDFW",  # Dallas-Fort Worth
    "KDEN",  # Denver
    "KLAX",  # Los Angeles
    "KORD",  # Chicago O'Hare
    "KJFK",  # New York JFK
    "KMCO",  # Orlando
    "KLAS",  # Las Vegas
    "KCLT",  # Charlotte
    "KMIA",  # Miami
    "KSEA",  # Seattle-Tacoma
    "KEWR",  # Newark
    "KSFO",  # San Francisco
    "KPHX",  # Phoenix
    "KIAH",  # Houston George Bush
    "KBOS",  # Boston
    "KFLL",  # Fort Lauderdale
    "KMSP",  # Minneapolis-Saint Paul
    "KLGA",  # New York LaGuardia
    "KDTW",  # Detroit
    "KPHL",  # Philadelphia
    "KSLC",  # Salt Lake City
    "KBWI",  # Baltimore
    "KDCA",  # Washington Reagan
    "KSAN",  # San Diego
    "KIAD",  # Washington Dulles
    "KTPA",  # Tampa
    "KBNA",  # Nashville
    "KAUS",  # Austin
    "KMDW",  # Chicago Midway
    "PHNL",  # Honolulu
    "KDAL",  # Dallas Love Field
    "KPDX",  # Portland
    "KSTL",  # St. Louis
    "KRDU",  # Raleigh-Durham
    "KHOU",  # Houston Hobby
    "KSMF",  # Sacramento
    "KMSY",  # New Orleans
    "KSJC",  # San Jose
    "KSNA",  # Santa Ana/Orange County
    "KMCI",  # Kansas City
    "KOAK",  # Oakland
    "KSAT",  # San Antonio
    "KRSW",  # Fort Myers
    "KCLE",  # Cleveland
    "KIND",  # Indianapolis
    "KPIT",  # Pittsburgh
    "KCVG",  # Cincinnati/Northern Kentucky
    "KCMH",  # Columbus
    "KPBI"   # West Palm Beach
]

current_time = datetime.now(timezone.utc)
reference_time = current_time.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
organized_metar_data = defaultdict(dict)
organized_taf_data = defaultdict(dict)
airport_extra_data = defaultdict(dict)

async def fetch_data(session, url):
    async with session.get(url) as response:
        if response.status == 200:
            return await response.json()
        else:
            print(f"Error: {response.status}")
            return None

async def fetch_metar_data(session, airport_codes, date):
    base_url = "https://aviationweather.gov/api/data/metar"
    ids = "%2C".join(airport_codes)
    url = f"{base_url}?ids={ids}&format=json&taf=false&date={date}"
    return await fetch_data(session, url)

async def fetch_taf_data(session, airport_codes, date):
    base_url = "https://aviationweather.gov/api/data/taf"
    ids = "%2C".join(airport_codes)
    url = f"{base_url}?ids={ids}&format=json&metar=false&time=valid&date={date}"
    return await fetch_data(session, url)

def categorize_weather(visibility, ceiling):
    #Categorize weather based on visibility and ceiling.
    #Visibility in statute miles, ceiling in feet.
    ceiling = int(ceiling)
    if type(visibility) is str:
        visibility = int(str(visibility).replace('+', ''))
    if visibility > 5 and ceiling > 3000:
        return "VFR"
    elif 3 <= visibility <= 5 or 1000 <= ceiling <= 3000:
        return "MVFR"
    elif 1 <= visibility < 3 or 500 <= ceiling < 1000:
        return "IFR"
    elif visibility < 1 or ceiling < 500:
        return "LIFR"

def extract_metar_weather_info(data):
    # Extract visibility
    dewpoint = data['dewp']
    temperature = data['temp']
    visibility = data['visib']
    if visibility == None:
        visibility = 10
    # Extract ceiling (lowest broken or overcast layer, or vertical visibility)
    ceiling = 100000
    for cloud in data.get('clouds', []):
        if cloud['cover'] in ['BKN', 'OVC']:
            ceiling = cloud['base']
            break
    
    # Extract wind speed and direction
    wind_speed = data['wspd']
    wind_direction = data['wdir']
    
    # Extract weather phenomena
    weather = data['wxString'] if data['wxString'] else 'None reported'
    
    flight_category = categorize_weather(visibility, ceiling)

    return {
        'dewpoint': dewpoint,
        'temperature': temperature,
        'visibility': visibility,
        'ceiling': ceiling,
        'wind_speed': wind_speed,
        'wind_direction': wind_direction,
        'weather': weather,
        'flight_category': flight_category
    }

def extract_taf_weather_info(data, target_timestamp):
    for forecast in data['fcsts']:
        if forecast['timeFrom'] <= target_timestamp < forecast['timeTo']:
            # Extract required weather information
            visibility = forecast['visib']
            if visibility == None:
                visibility = 10
            ceiling = 100000
            for cloud in forecast.get('clouds', []):
                if cloud['cover'] in ['BKN', 'OVC']:
                    ceiling = cloud['base']
                    break
            
            wind_direction = forecast['wdir']
            wind_speed = forecast['wspd']
            weather = forecast['wxString'] if forecast['wxString'] else 'None reported'
            
            flight_category = categorize_weather(visibility, ceiling)

            return {
                'visibility': visibility,
                'ceiling': ceiling,
                'wind_direction': wind_direction,
                'wind_speed': wind_speed,
                'weather': weather,
                'flight_category': flight_category
            }
    
    return None

def organize_metar_data(data, airport_extra_data):
    for entry in data:
        icao_id = entry['icaoId']
        report_time = entry['reportTime']
        
        weather_info = extract_metar_weather_info(entry)
        
        # Add extra airport data
        if icao_id in airport_extra_data:
            weather_info.update({
                'altitude': airport_extra_data[icao_id]['altitude'],
                'latitude': airport_extra_data[icao_id]['latitude'],
                'longitude': airport_extra_data[icao_id]['longitude'],
                'distance_to_water': airport_extra_data[icao_id]['distance_to_water']
            })
        
        organized_metar_data[icao_id][report_time] = weather_info

def organize_taf_data(data, unix_time, airport_extra_data):
    for entry in data:
        icao_id = entry['icaoId']
        bulletin_time = entry['bulletinTime']
        
        weather_info = extract_taf_weather_info(entry, unix_time)
        
        # Add extra airport data
        if icao_id in airport_extra_data and weather_info:
            weather_info.update({
                'altitude': airport_extra_data[icao_id]['altitude'],
                'latitude': airport_extra_data[icao_id]['latitude'],
                'longitude': airport_extra_data[icao_id]['longitude'],
                'distance_to_water': airport_extra_data[icao_id]['distance_to_water']
            })
        
        organized_taf_data[icao_id][bulletin_time] = weather_info

def convert_to_unix_timestamp(time_str):
    # Parse the string into a datetime object
    dt = datetime.strptime(time_str, "%Y%m%d_%H%M%SZ")
    
    # Convert to Unix timestamp
    unix_timestamp = calendar.timegm(dt.utctimetuple())
    
    return unix_timestamp

async def process_data(session, time, airport_extra_data):
    formatted_time = time.strftime("%Y%m%d_%H%M%S") + "Z"
    print('Processing data ...', time)
    
    metar_task = fetch_metar_data(session, top_50_airports_icao, formatted_time)
    taf_task = fetch_taf_data(session, top_50_airports_icao, formatted_time)
    
    metar_data, taf_data = await asyncio.gather(metar_task, taf_task)
    
    if metar_data:
        organize_metar_data(metar_data, airport_extra_data)
    if taf_data:
        organize_taf_data(taf_data, convert_to_unix_timestamp(formatted_time), airport_extra_data)

def sort_weather_data(data):
    sorted_weather_data = defaultdict(dict)

    for airport, airport_data in data.items():
        # Sort the dates for each airport
        sorted_dates = sorted(airport_data.keys(), key=lambda x: datetime.strptime(x, "%Y-%m-%d %H:%M:%S"), reverse=True)
        
        # Rebuild the dictionary with sorted dates
        for date in sorted_dates:
            sorted_weather_data[airport][date] = airport_data[date]

    return sorted_weather_data

def get_airport_info(airport_codes):
    airports_db = Airports()
    
    airport_info = {}
    for code in airport_codes:
        if code == 'HNL':
            full_code = 'PHNL'
        else:
            full_code = 'K' + code
        
        airport = airports_db.lookup(code)
        if airport:
            airport_info[full_code] = {
                'altitude': airport.alt,
                'latitude': airport.lat,
                'longitude': airport.lon
            }
        else:
            airport_info[full_code] = f"Airport {full_code} not found"
    
    return airport_info

async def find_nearest_water(session, lat, lon):
    url = f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?keyword=beach&location={lat},{lon}&radius=30000&key={API_KEY}"
    async with session.get(url) as response:
        data = await response.json()

    if data['status'] == 'OK' and data['results']:
        nearest_water = data['results'][0]['geometry']['location']
        return nearest_water['lat'], nearest_water['lng']
    else:
        # If not able to find within the range of 30km, return fodder values
        return 1, 1

async def process_airport(session, icao, data):
    lat, lon = await find_nearest_water(session, data['latitude'], data['longitude'])
    distance = haversine_distance(data['latitude'], data['longitude'], lat, lon)
    data['distance_to_water'] = round(distance, 2)

    return icao, data

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371  # Earth's radius in kilometers
    
    lat1, lon1, lat2, lon2 = map(radians, [float(lat1), float(lon1), float(lat2), float(lon2)])
    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a)) 
    distance = R * c

    return distance

def get_error_type(metar_category, taf_category):
    category_rank = {'VFR': 0, 'MVFR': 1, 'IFR': 2, 'LIFR': 3}
    
    if metar_category == taf_category:
        return "Correct - No error (0)"
    elif category_rank[taf_category] > category_rank[metar_category]:
        return "False Alarm - Type I (1) error"
    else:
        return "Fail to Detect - Type II (2) error"

def merge_metar_taf(metar_data, taf_data):
    merged_data = {}

    for airport in metar_data.keys():
        merged_data[airport] = {}
        
        metar_items = list(metar_data[airport].items())
        taf_items = list(taf_data[airport].items())
        
        for (metar_timestamp, metar), (taf_timestamp, taf) in zip(metar_items, taf_items):
            merged_entry = {
                "Type_METAR": "METAR",
                "Dewpoint_METAR (C)": metar.get('dewpoint'),
                "Temperature_METAR (C)": metar.get('temperature'),
                "Visibility_METAR (km)": metar.get('visibility'),
                "Ceiling_METAR (ft)": metar.get('ceiling'),
                "Wind_speed_METAR (kt)": metar.get('wind_speed'),
                "Wind_direction_METAR (degrees)": metar.get('wind_direction'),
                "Weather_METAR ": metar.get('weather'),
                "Flight_category_METAR": metar.get('flight_category'),
                "Type_TAF": "TAF",
                "Visibility_TAF (km)": taf.get('visibility'),
                "Ceiling_TAF (ft)": taf.get('ceiling'),
                "Wind_speed_TAF (kt)": taf.get('wind_speed'),
                "Wind_direction_TAF (ddegrees)": taf.get('wind_direction'),
                "Weather_TAF": taf.get('weather'),
                "Flight_category_TAF": taf.get('flight_category'),
                "Altitude (ft)": taf.get('altitude'),
                "Latitude (degrees)": taf.get('latitude'),
                "Longitude (degrees)": taf.get('longitude'),
                "Distance (km)": taf.get('distance_to_water')
            }
            
            metar_category = metar.get('flight_category')
            taf_category = taf.get('flight_category')
            merged_entry["Error_type"] = get_error_type(metar_category, taf_category)
            
            merged_data[airport][metar_timestamp] = merged_entry

    return merged_data

def export_to_csv(merged_data, output_file='merged_metar_taf.csv'):
    # Get the first airport and timestamp to extract headers
    first_airport = next(iter(merged_data))
    first_timestamp = next(iter(merged_data[first_airport]))
    sample_data = merged_data[first_airport][first_timestamp]

    # Generate headers dynamically
    headers = ['Airport', 'DateTime'] + list(sample_data.keys())

    all_data = []

    # Read existing entries if the file exists
    if os.path.exists(output_file):
        with open(output_file, 'r', newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                all_data.append(row)

    # Append the new data
    for airport, timestamps in merged_data.items():
        for timestamp, data in timestamps.items():
            row = {
                "Airport": airport,
                "DateTime": timestamp,
                **data  # This unpacks all the data fields
            }
            all_data.append(row)

    # Sort by 'Airport' and 'DateTime'
    all_data.sort(key=lambda x: (x['Airport'], datetime.strptime(x['DateTime'], '%Y-%m-%d %H:%M:%S')), reverse=True)

    # Convert values like "-RA" or "-SHRA" or "+RA" or "-157.922428" to be explicitly treated as text
    for row in all_data:
        for key, value in row.items():
            if isinstance(value, str) and (value.startswith('-') or value.startswith('+')):
                row[key] = f"'{value}"  # Prefix the value with a single quote

    # Write sorted data to CSV file
    with open(output_file, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=headers)
        writer.writeheader()
        writer.writerows(all_data)

    print(f"Data exported to {output_file}")

async def main():
    airport_codes = [code[1:] for code in top_50_airports_icao]  # Remove the first character
    airport_extra_data = get_airport_info(airport_codes)
    
    async with aiohttp.ClientSession() as session:
        tasks = [process_airport(session, icao, data) for icao, data in airport_extra_data.items()]
        results = await asyncio.gather(*tasks)
    
    airport_extra_data = dict(results)

    async with aiohttp.ClientSession() as session:
        tasks = []
        for day in range(14):  # 0 to 13 days
            for hour in [6, 12, 18, 24]:
                time = reference_time - timedelta(days=day, hours=hour)
                tasks.append(process_data(session, time, airport_extra_data))
        await asyncio.gather(*tasks)

    sorted_metar_weather_data = sort_weather_data(organized_metar_data)
    sorted_taf_weather_data = sort_weather_data(organized_taf_data)

    merged_data = merge_metar_taf(sorted_metar_weather_data, sorted_taf_weather_data)

    export_to_csv(merged_data)

if __name__ == "__main__":
    asyncio.run(main())