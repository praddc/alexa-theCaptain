from datetime import datetime
import time

from BeautifulSoup import BeautifulSoup
from lxml import etree, html
import pytz
import requests

import utils


def get_weather(body_of_water):
    if body_of_water == 'lake washington':
        return king_county_buoy(body_of_water)
    elif body_of_water == 'lake sammamish':
        return king_county_buoy(body_of_water)
    elif body_of_water == 'lake union':
        return lake_union_weather()
    else:
        return "I'm sorry, I couldn't find that body of water"


# If we're getting the data from the Lake Union Weather webpage
def lake_union_weather():
    url_to_use = 'https://lakeunionweather.info'
    page = requests.get(url_to_use)
    soup = BeautifulSoup(page.content)
    try:
        header_data = soup.findAll("div", {"id": "Header"})[0]
        atmosphere_data = soup.findAll("table", {"id": "WeatherTable"})[0]
        water_data = soup.findAll("table", {"id": "WaterTable"})[0]
    except IndexError:
        pass

    # First lets get the date and time out of this
    info_date = None
    date_data = header_data.findAll('h4')[0]
    date_data = BeautifulSoup("{}".format(date_data)).getText()
    date_string = date_data.split('recorded on')[1].strip()
    info_date = datetime.strptime(date_string, "%d %b %Y %I:%M %p")

    # This is a gross way to get all the data from the table, but so it goes
    air_temp_f = None
    wind_chill_f = None
    avg_windspeed_dir = None
    avg_windspeed_mph = None
    for tr in BeautifulSoup("{}".format(atmosphere_data)).findAll('tr')[1:]:
        ths = BeautifulSoup("{}".format(tr.findAll('th')[0])).getText()
        tds = BeautifulSoup("{}".format(tr.findAll('td')[0])).getText()
        if ths.find('Temperature') >= 0:
            air_temp_f = float(tds.split('&#176;F')[0])
        elif ths.find('Wind Chill') >= 0:
            wind_chill_f = float(tds.split('&#176;F')[0])
        elif ths.find('Av. Windspeed') >= 0:
            avg_windspeed_mph = float(tds.split('MPH')[0].strip())
            avg_windspeed_dir = tds.split('from the')[1].strip()

        # This is a gross way to get all the data from the table, but so it goes
    water_temp_f = None
    for tr in BeautifulSoup("{}".format(water_data)).findAll('tr')[1:]:
        tds = tr.findAll('td')
        if float(BeautifulSoup("{}".format(tds[0])).getText()) < 5:
            water_temp_f = float(BeautifulSoup("{}".format(tds[1])).getText())

    # Now let's find the time diff when we got this
    if info_date is None:
        time_string = ""
    else:
        # Need to make this aware of the time zone
        tz = pytz.timezone('US/Pacific')
        latest_date_tz = tz.localize(info_date)
        time_diff = datetime.now(tz) - latest_date_tz
        # time_diff = datetime.now() - latest_date_water_temp
        if time_diff.days > 0:
            hours_diff = time_diff.days * 24
            hours_diff += time_diff.seconds / 60 / 60
        else:
            hours_diff = time_diff.seconds / 60 / 60
        time_string = " about {} hours ago".format(hours_diff)

    if air_temp_f is None and water_temp_f is None:
        # This means we didn't find anythiing
        retval = "I'm sorry, I couldn't find any recent data about the weather on lake union"
    else:
        retval = "Last known conditions on lake union include: "
        num_values = 0
        if air_temp_f is not None:
            retval += "Water temperature of {:.0f} degrees fahrenheit".format(round(air_temp_f))
            num_values += 1
        if air_temp_f is not None:
            if num_values > 0:
                retval += ", and "
            retval += "Air temperature of {:.0f} degrees fahrenheit, ".format(round(air_temp_f))
            retval += "Wind chill of {:.0f} degrees fahrenheit, ".format(round(wind_chill_f))
            retval += "wind speed of {:.0f} miles per hour ".format(round(utils.mps_to_mph(avg_windspeed_mph), 1))
            retval += "coming from the {}".format(utils.compass_to_words(avg_windspeed_dir))
        retval += "{}".format(time_string)
    return retval


# If we're getting the data from King County buoy data
def king_county_buoy(body_of_water):
    if body_of_water == 'lake washington':
        buoy = 'wa'
    elif body_of_water == 'lake sammamish':
        buoy = 'samm'
    else:
        return "I'm sorry, I couldn't find that body of water"

    water_temp_url = 'https://green2.kingcounty.gov/lake-buoy/DataScrape.aspx?type=profile&buoy={}&year={}&month={}'
    air_temp_url = 'https://green2.kingcounty.gov/lake-buoy/DataScrape.aspx?type=met&buoy={}&year={}&month={}'

    # Of course we need to get the local timezones, since the buoy data is local to pacific
    tz = pytz.timezone('US/Pacific')
    dt = datetime.fromtimestamp(time.time(), tz)
    current_month = dt.strftime('%m')
    current_year = dt.strftime("%Y")

    # First let's get the water temperature from the buoy data
    # We're going to get back this awesome ASPX table that we'll have to disect
    url_to_use = water_temp_url.format(buoy, current_year, current_month)
    r = requests.get(url_to_use)
    table_start = r.content.find('<table')
    table_end = r.content.find('</table>') + 8
    table_string = r.content[table_start:table_end]

    # Now we have the string from the response that is the table.
    # Let's look for the latest temp at a reasonable (< 1.5m) depth. Record the date/time/temp
    latest_date_water_temp = datetime.strptime('01/01/2000', "%m/%d/%Y")
    # latest_depth = 0
    latest_temp_water = 0

    table = etree.XML(table_string)
    rows = iter(table)
    headers = [col.text for col in next(rows)]
    for row in rows:
        values = [col.text for col in row]
        row_dict = dict(zip(headers, values))
        if float(row_dict.get('Depth (m)')) < 1.5:
            temp_c = float(row_dict.get(u'Temperature (\xb0C)'))
            temp_f = temp_c * 1.8 + 32
            date_object = datetime.strptime(row_dict.get('Date'), "%m/%d/%Y %I:%M:%S %p")
            if date_object >= latest_date_water_temp:
                latest_date_water_temp = date_object
                # latest_depth = row_dict.get('Depth (m)')
                latest_temp_water = temp_f
    # Excellent, now we have our most recent water temp
    latest_temp_water = round(latest_temp_water, 1)

    # Now let's get the air temperature from the buoy data
    # We're going to get back this awesome ASPX table that we'll have to disect
    url_to_use = air_temp_url.format(buoy, current_year, current_month)
    r = requests.get(url_to_use)
    table_start = r.content.find('<table')
    table_end = r.content.find('</table>') + 8
    table_string = r.content[table_start:table_end]

    # Now we have the string from the response that is the table.
    # Let's look for the latest temp at a reasonable (< 1.5m) depth. Record the date/time/temp
    latest_date_air_temp = datetime.strptime('01/01/2000', "%m/%d/%Y")
    latest_temp_air = 0
    latest_wind_air_speed = 0
    latest_wind_air_dir = ''

    table = etree.XML(table_string)
    rows = iter(table)
    headers = [col.text for col in next(rows)]
    for row in rows:
        values = [col.text for col in row]
        row_dict = dict(zip(headers, values))
        temp_c = float(row_dict.get(u'Air Temperature (\xb0C)'))
        temp_f = temp_c * 1.8 + 32
        date_object = datetime.strptime(row_dict.get('Date'), "%m/%d/%Y %I:%M:%S %p")
        if date_object >= latest_date_air_temp:
            latest_date_air_temp = date_object
            latest_temp_air = temp_f
            latest_wind_air_speed = float(row_dict.get(u'Wind Speed (m/sec)'))
            latest_wind_air_dir = float(row_dict.get(u'Wind Direction (degrees)'))
    # Excellent, now we have our most recent water temp
    latest_temp_air = round(latest_temp_air, 1)

    if latest_date_water_temp == datetime.strptime('01/01/2000', "%m/%d/%Y") and \
       latest_date_air_temp == datetime.strptime('01/01/2000', "%m/%d/%Y"):
        # This means we didn't find anythiing
        retval = "I'm sorry, I couldn't find any recent data about the weather on {}".format(body_of_water)
    else:
        retval = "Last known conditions on {} include: ".format(body_of_water)
        num_values = 0
        if latest_date_water_temp != datetime.strptime('01/01/2000', "%m/%d/%Y"):
            # Need to make this aware of the time zone
            tz = pytz.timezone('US/Pacific')
            latest_date_tz = tz.localize(latest_date_water_temp)
            time_diff = datetime.now(tz) - latest_date_tz
            # time_diff = datetime.now() - latest_date_water_temp
            if time_diff.days > 0:
                hours_diff = time_diff.days * 24
                hours_diff += time_diff.seconds / 60 / 60
            else:
                hours_diff = time_diff.seconds / 60 / 60
            retval += "Water temperature of {:.0f} degrees fahrenheit about {} hours ago".format(round(latest_temp_water),
                                                                                             hours_diff)
            num_values += 1
        if latest_date_air_temp != datetime.strptime('01/01/2000', "%m/%d/%Y"):
            # Need to make this aware of the time zone
            tz = pytz.timezone('US/Pacific')
            latest_date_tz = tz.localize(latest_date_air_temp)
            time_diff = datetime.now(tz) - latest_date_tz
            # time_diff = datetime.now() - latest_date_water_temp
            if time_diff.days > 0:
                hours_diff = time_diff.days * 24
                hours_diff += time_diff.seconds / 60 / 60
            else:
                hours_diff = time_diff.seconds / 60 / 60
            if num_values > 0:
                retval += ", and "
            retval += "Air temperature of {:.0f} degrees fahrenheit, ".format(round(latest_temp_air))
            retval += "wind speed of {:.0f} miles per hour ".format(round(utils.mps_to_mph(latest_wind_air_speed), 1))
            retval += "coming from the {}".format(utils.compass_to_words(utils.deg_to_compass(latest_wind_air_dir)))
            retval += "about {} hours ago".format(hours_diff)
    return retval
