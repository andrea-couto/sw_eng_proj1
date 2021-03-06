'''
THIS FILE PUSHES FILTERED DATA FROM HACKER NEWS TO FIREBASE DATABASE
CREATES TWO FILES LOCATION_1.CSV & LOCATION_2.CSV
THESE FILES CONTAIN LOCATION DATA EXTRACTED FROM HACKER NEWS WHO IS HIRING FORUMS
AUTHOR: ANDY COUTO
'''

import requests
from html.parser import HTMLParser
import sys
from firebase import firebase
from geopy.geocoders import Nominatim
from geotext import GeoText
import datetime


class MLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs = True
        self.fed = []

    def handle_data(self, d):
        self.fed.append(d)

    def get_data(self):
        return ''.join(self.fed)


def strip_tags(html):
    s = MLStripper()
    s.feed(html)
    return s.get_data()


# TODO make filter variables like points = 100; points_query = f'hitsPerPage={points}'
# then pass points_query inside filter_for_object_query
def establish_web_response(search_query):
    web_response = requests.get(search_query)
    if web_response.status_code == 200:
        return web_response
    else:
        return print("Error getting web response: %s", web_response.status_code)


def get_json_hits(web_response):
    json_data = web_response.json()
    json_hits = json_data['hits']  # looks at only the first dictionary with the data we want
    return json_hits


def extract_info(json_hits):
    title_id = {}
    list_of_valid_hits = []  # store the valid objectIds
    for hits in json_hits:
        if hits['title'] is not None and hits['points'] > 100:
            title = hits['title']
            title = title[title.find("(") + 1:title.find(")")]  # get only the month and year
            title_id[hits['objectID']] = title  # add month year and id to dict
            list_of_valid_hits.append(hits['objectID'])
    return title_id, list_of_valid_hits


def update_languages(cleaned_comment, languages, keys):
    for i in keys:
        if i in cleaned_comment:
            languages[i] += 1


def remove_values(unfiltered_list, value):
    while value in unfiltered_list:
        unfiltered_list.remove(value)

def print_uploading(i, ids):
    percent = ((i + 1) / len(ids)) * 100
    sys.stdout.write("\rUploading to firebase: %d%% complete" % percent)
    sys.stdout.flush()


def get_locations_for_year(found_entities):
    locations = {}
    for comment_cities in found_entities:
        if len(comment_cities) > 0:
            possible_city = comment_cities[0].capitalize()
            if possible_city not in locations:
                locations[possible_city] = 1
            else:
                locations[possible_city] += 1
    return locations


def reset_values():
    languages = {
        'python': 0,
        ' c ': 0,
        ' c, ': 0,
        ' java ': 0,
        ' java, ': 0,
        ' java. ': 0,
        'c++': 0,
        'c#': 0,
        ' r ': 0,
        ' r, ': 0,
        'javascript': 0,
        'php': 0,
        ' go ': 0,
        ' go, ': 0,
        'swift': 0
    }
    keys = languages.keys()
    num_comments = 0
    onsite = 0
    remote = 0
    return languages, keys, num_comments, onsite, remote


#TODO ENFORCE UTF-8 ENCODING
def write_difference_file(locations_1, locations_2, geolocator):
    file = open("difference_in_jobs.csv", "w")
    file.write("city,latitude,longitude,original,difference\n")
    for key in locations_1.keys():
        if key in locations_2.keys():
            valid_geocode = True
            lat, long = "", ""
            difference = locations_1[key] - locations_2[key]
            difference_percent = round((difference/locations_1[key])*100, 2)
            if key == 'San francisco':
                lat = "37.7749"
                long = "-122.4194"
            else:
                resulting_geocode = geolocator.geocode(key)  # if problem can add timeout=None
                if resulting_geocode is not None:
                    lat = str(resulting_geocode.latitude)
                    long = str(resulting_geocode.longitude)
                else:
                    valid_geocode = False
            if valid_geocode:
                file.write(key + "," + lat + "," + long + "," + str(locations_1[key]) + "," + str(difference_percent) + "\n")
        else:
            resulting_geocode = geolocator.geocode(key)  # if problem can add timeout=None
            if resulting_geocode is not None:
                lat = str(resulting_geocode.latitude)
                long = str(resulting_geocode.longitude)
                file.write(key + "," + lat + "," + long + "," + str(locations_1[key]) + "," + "100" + "\n")
    file.close()


def main():
    HN_database = firebase.FirebaseApplication('https://hackernewsgraphs.firebaseio.com/', None)
    response = establish_web_response('https://hn.algolia.com/api/v1/search_by_date?query=%22Ask%20HN%20:%20Who%20is%20hiring%3F%22&hitsPerPage=100&numericFilters=created_at_i>1454338862')
    json_hits = get_json_hits(response)
    titles, ids = extract_info(json_hits)
    get_url = 'http://hn.algolia.com/api/v1/items/'
    geolocator = Nominatim()
    userTime = datetime.datetime.now()
    userMonth = userTime.strftime("%B")
    userYear = userTime.year
    this_year = (userMonth + " " + str(userYear))
    last_year = (userMonth + " " + str(userYear-1))
    this_yr_locations, last_yr_locations = [], []
    data_to_remove = ['Mongo', 'Most', 'Spring', 'Lutz', 'VAN', 'Of', 'Fleet', 'Opportunity']

    HN_database.delete('', '')

    for i in range(len(ids)):
        month_url = requests.get(get_url + str(ids[i])).json()
        month_title = titles[str(month_url['id'])]
        get_coord = False
        if month_title == this_year or month_title == last_year:
            get_coord = True
        children = month_url['children']
        languages, keys, num_comments, onsite, remote = reset_values()

        for comment in children:
            if comment is not None and comment['parent_id'] == month_url['id']:
                if comment['text'] is not None:
                    if get_coord:
                        places = GeoText(comment['text'])
                        cities = places.cities
                        for data in data_to_remove:
                            remove_values(cities, data)
                        if month_title == this_year:
                            this_yr_locations.append(cities)
                        elif month_title == last_year:
                            last_yr_locations.append(cities)
                    cleaned_comment = strip_tags(comment['text'].lower())
                    if 'onsite' or 'on-site' in cleaned_comment:
                        onsite += 1
                    if 'remote' in cleaned_comment:
                        remote += 1
                    num_comments += 1
                    update_languages(cleaned_comment, languages, keys)

        print_uploading(i, ids)

        HN_database.post('/num_comments', {month_title: num_comments})

        HN_database.post('/onsite', {month_title: onsite})
        HN_database.post('/remote', {month_title: remote})

        HN_database.post('/python', {month_title: languages['python']})
        c = languages[' c '] + languages[' c, ']
        HN_database.post('/c', {month_title: c})
        java = languages[' java '] + languages[' java, '] + languages[' java. ']
        HN_database.post('/java', {month_title: java})
        HN_database.post('/cplusplus', {month_title: languages['c++']})
        HN_database.post('/csharp', {month_title: languages['c#']})
        r = languages[' r '] + languages[' r, ']
        HN_database.post('/r', {month_title: r})
        HN_database.post('/javascript', {month_title: languages['javascript']})
        HN_database.post('/php', {month_title: languages['php']})
        go = languages[' go '] + languages[' go, ']
        HN_database.post('/go', {month_title: go})
        HN_database.post('/swift', {month_title: languages['swift']})

    sys.stdout.write("\rcreating job difference csv file...")
    sys.stdout.flush()

    locations_1 = get_locations_for_year(this_yr_locations)
    locations_2 = get_locations_for_year(last_yr_locations)

    write_difference_file(locations_1, locations_2, geolocator)


if __name__ == '__main__':
    main()