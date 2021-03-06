#
# Copyright (c) 2017 Jonathan Weyn <jweyn@uw.edu>
#
# See the file LICENSE for your rights.
#

"""
Retrieve verification from MesoWest, NWS CF6 files, and NCDC data.
"""

from .MesoPy import Meso
import pandas as pd
import numpy as np
import os
import re
from thetae.util import meso_api_dates, Daily
from datetime import datetime, timedelta
import requests
from builtins import str


def get_cf6_files(config, stid, num_files=1):
    """
    After code by Luke Madaus

    Retrieves CF6 climate verification data released by the NWS. Parameter num_files determines how many recent files
    are downloaded.
    """

    # Create directory if it does not exist
    site_directory = '%s/site_data' % config['THETAE_ROOT']
    if config['debug'] > 50:
        print('get_cf6_files: accessing site data in %s' % site_directory)

    # Construct the web url address. Check if a special 3-letter station ID is provided.
    nws_url = 'http://forecast.weather.gov/product.php?site=NWS&issuedby=%s&product=CF6&format=TXT'
    try:
        stid3 = config['Stations'][stid]['station_id3']
    except KeyError:
        stid3 = stid[1:].upper()
    nws_url = nws_url % stid3

    # Determine how many files (iterations of product) we want to fetch
    if num_files == 1:
        print('get_cf6_files: retrieving latest CF6 file for %s' % stid)
    else:
        print('get_cf6_files: retrieving %s archived CF6 files for %s' % (num_files, stid))

    # Fetch files
    for r in range(1, num_files + 1):
        # Format the web address: goes through 'versions' on NWS site which correspond to increasingly older files
        version = 'version=%d&glossary=0' % r
        nws_site = '&'.join((nws_url, version))
        if config['debug'] > 50:
            print('get_cf6_files: fetching from %s' % nws_site)
        response = requests.get(nws_site)
        cf6_data = response.text

        # Remove the header
        try:
            body_and_footer = cf6_data.split('CXUS')[1]  # Mainland US
        except IndexError:
            try:
                body_and_footer = cf6_data.split('CXHW')[1]  # Hawaii
            except IndexError:
                try:
                    body_and_footer = cf6_data.split('CXAK')[1]  # Alaska
                except IndexError:
                    if config['debug'] > 50:
                        print('get_cf6_files: bad file from request version %d' % r)
                    continue
        body_and_footer_lines = body_and_footer.splitlines()
        if len(body_and_footer_lines) <= 2:
            body_and_footer = cf6_data.split('000')[2]

        # Remove the footer
        body = body_and_footer.split('[REMARKS]')[0]

        # Find the month and year of the file
        try:
            current_year = re.search('YEAR: *(\d{4})', body).groups()[0]
        except BaseException:
            if config['debug'] > 9:
                print('get_cf6_files warning: file from request version %d is faulty' % r)
            continue
        try:
            current_month = re.search('MONTH: *(\D{3,9})', body).groups()[0]
            current_month = current_month.strip()  # Gets rid of newlines and whitespace
            datestr = '%s %s' % (current_month, current_year)
            file_date = datetime.strptime(datestr, '%B %Y')
        except:  # Some files have a different formatting, although this may be fixed now.
            current_month = re.search('MONTH: *(\d{2})', body).groups()[0]
            current_month = current_month.strip()
            datestr = '%s %s' % (current_month, current_year)
            file_date = datetime.strptime(datestr, '%m %Y')

        # Write to a temporary file, check if output file exists, and if so, make sure the new one has more data
        datestr = file_date.strftime('%Y%m')
        filename = '%s/%s_%s.cli' % (site_directory, stid.upper(), datestr)
        temp_file = '%s/temp.cli' % site_directory
        with open(temp_file, 'w') as out:
            out.write(body)

        def file_len(file_name):
            with open(file_name) as f:
                for i, l in enumerate(f):
                    pass
                return i + 1

        if os.path.isfile(filename):
            old_file_len = file_len(filename)
            new_file_len = file_len(temp_file)
            if old_file_len < new_file_len:
                if config['debug'] > 9:
                    print('get_cf6_files: overwriting %s' % filename)
                os.remove(filename)
                os.rename(temp_file, filename)
            else:
                if config['debug'] > 9:
                    print('get_cf6_files: %s already exists' % filename)
        else:
            if config['debug'] > 9:
                print('get_cf6_files: writing %s' % filename)
            os.rename(temp_file, filename)


def _cf6_wind(config, stid):
    """
    After code by Luke Madaus

    This function is used internally only.

    Generates wind verification values from climate CF6 files stored in site_directory. These files can be generated
    by _get_cf6_files.
    """

    site_directory = '%s/site_data' % config['THETAE_ROOT']
    if config['debug'] > 9:
        print('verification: searching for CF6 files in %s' % site_directory)
    listing = os.listdir(site_directory)
    file_list = [f for f in listing if f.startswith(stid.upper()) and f.endswith('.cli')]
    file_list.sort()
    if len(file_list) == 0:
        raise IOError('No CF6 files found in %s for site %s.' % (site_directory, stid))
    if config['debug'] > 50:
        print('verification: found %d CF6 files' % len(file_list))

    # Interpret CF6 files
    if config['debug'] > 50:
        print('verification: reading CF6 files')
    cf6_values = {}
    for file in file_list:
        year, month = re.search('(\d{4})(\d{2})', file).groups()
        open_file = open('%s/%s' % (site_directory, file), 'r')
        for line in open_file:
            matcher = re.compile('( \d|\d{2}) ( \d{2}|-\d{2}|  \d| -\d|\d{3})')
            if matcher.match(line):
                # We've found an obs line!
                lsp = line.split()
                day = int(lsp[0])
                date = datetime(int(year), int(month), day)
                cf6_values[date] = {}
                # Get only the wind value
                if lsp[11] == 'M':
                    cf6_values[date]['wind'] = 0.0
                else:
                    cf6_values[date]['wind'] = float(lsp[11]) * 0.868976

    return cf6_values


def _climo_wind(config, stid, dates=None):
    """
    This function is used internally only.

    Fetches climatological wind data using ulmo package to retrieve NCDC archives.
    """

    import ulmo
    from thetae.util import get_ghcn_stid

    ghcn_stid = get_ghcn_stid(config, stid)

    if config['debug'] > 0:
        print('verification: fetching wind data for %s from NCDC (may take a while)' % ghcn_stid)
    v = 'WSF2'
    D = ulmo.ncdc.ghcn_daily.get_data(ghcn_stid, as_dataframe=True, elements=[v])
    wind_dict = {}
    if dates is None:
        dates = list(D[v].index.to_timestamp().to_pydatetime())
    for date in dates:
        wind_dict[date] = {'wind': D[v].loc[date]['value'] / 10. * 1.94384}

    return wind_dict


def get_verification(config, stid, start, end, use_climo=False, use_cf6=True):
    """
    Generates verification data from MesoWest API. If use_climo is True, then fetch climate data from NCDC using ulmo
    to fill in wind values. (We probably generally don't want to do this, because it is slow and is delayed by 1-2
    weeks from present.) If use_cf6 is True, then any CF6 files found in ~/site_data will be used for wind values.
    These files are retrieved by get_cf6_files.
    """

    # MesoWest token and init
    meso_token = config['Verify']['api_key']
    m = Meso(token=meso_token)
    if config['debug'] > 9:
        print('verification: MesoPy initialized for station %s' % stid)

    # Look for desired variables
    vars_request = ['air_temp', 'wind_speed', 'precip_accum_one_hour']
    vars_option = ['air_temp_low_6_hour', 'air_temp_high_6_hour', 'precip_accum_six_hour']

    # Add variables to the api request if they exist
    if config['debug'] > 50:
        print('verification: searching for 6-hourly variables')
    latest = m.latest(stid=stid)
    obs_list = list(latest['STATION'][0]['SENSOR_VARIABLES'].keys())
    for var in vars_option:
        if var in obs_list:
            if config['debug'] > 9:
                print('verification: using variable %s' % var)
            vars_request += [var]
    vars_api = ','.join(vars_request)

    # Units
    units = 'temp|f,precip|in,speed|kts'

    # Retrieve data
    print('verification: retrieving data from %s to %s' % (start, end))
    obs = m.timeseries(stid=stid, start=start, end=end, vars=vars_api, units=units)
    obspd = pd.DataFrame.from_dict(obs['STATION'][0]['OBSERVATIONS'])

    # Rename columns to requested vars. This changes the columns in the DataFrame to corresponding names in
    # vars_request, because otherwise the columns returned by MesoPy are weird.
    obs_var_names = obs['STATION'][0]['SENSOR_VARIABLES']
    obs_var_keys = list(obs_var_names.keys())
    col_names = list(map(''.join, obspd.columns.values))
    for c in range(len(col_names)):
        col = col_names[c]
        for k in range(len(obs_var_keys)):
            key = obs_var_keys[k]
            if col == list(obs_var_names[key].keys())[0]:
                col_names[c] = key
    obspd.columns = col_names

    # Let's add a check here to make sure that we do indeed have all of the variables we want
    for var in vars_request:
        if var not in col_names:
            obspd = obspd.assign(**{var: np.nan})

    # Change datetime column to datetime object, subtract 6 hours to use 6Z days
    dateobj = pd.Index(pd.to_datetime(obspd['date_time'])).tz_localize(None) - timedelta(hours=6)
    obspd['date_time'] = dateobj
    datename = 'DATETIME'
    obspd = obspd.rename(columns={'date_time': datename})

    # Now we're going to group the data into daily values. First, we group by hour to be sure we have the right
    # precipitation accumulations, which are officially recorded by hour.

    def hour(dates):
        date = dates.iloc[0]
        return datetime(date.year, date.month, date.day, date.hour)

    # Define an aggregation function for pandas groupby
    aggregate = {datename: hour}
    if 'air_temp_high_6_hour' in vars_request and 'air_temp_low_6_hour' in vars_request:
        aggregate['air_temp_high_6_hour'] = np.max
        aggregate['air_temp_low_6_hour'] = np.min
    aggregate['air_temp'] = {'air_temp_max': np.max, 'air_temp_min': np.min}
    if 'precip_accum_six_hour' in vars_request:
        aggregate['precip_accum_six_hour'] = np.max
    aggregate['wind_speed'] = np.max
    aggregate['precip_accum_one_hour'] = np.max

    if config['debug'] > 50:
        print('verification: grouping data by hour')
    obs_hourly = obspd.groupby([pd.DatetimeIndex(obspd[datename]).year,
                                pd.DatetimeIndex(obspd[datename]).month,
                                pd.DatetimeIndex(obspd[datename]).day,
                                pd.DatetimeIndex(obspd[datename]).hour]).agg(aggregate)

    # Rename columns
    col_names = obs_hourly.columns.values
    col_names_new = []
    for c in range(len(col_names)):
        if col_names[c][0] == 'air_temp':
            col_names_new.append(col_names[c][1])
        else:
            col_names_new.append(col_names[c][0])
    obs_hourly.columns = col_names_new

    # Now group by day. Note that we changed the time to subtract 6 hours, so days are nicely defined as 6Z to 6Z.
    def day(dates):
        date = dates.iloc[0]
        return datetime(date.year, date.month, date.day)

    aggregate[datename] = day
    aggregate['air_temp_min'] = np.min
    aggregate['air_temp_max'] = np.max
    aggregate['precip_accum_six_hour'] = np.sum
    try:
        aggregate.pop('air_temp')
    except:
        pass

    if config['debug'] > 50:
        print('verification: grouping data by day')
    obs_daily = obs_hourly.groupby([pd.DatetimeIndex(obs_hourly[datename]).year,
                                    pd.DatetimeIndex(obs_hourly[datename]).month,
                                    pd.DatetimeIndex(obs_hourly[datename]).day]).agg(aggregate)

    # Now we check for wind values from the CF6 files, which are the actual verification
    if use_climo or use_cf6:
        if config['debug'] > 9:
            print('verification: checking climo and/or CF6 for wind data')
        climo_values = {}
        cf6_values = {}
        if use_climo:
            try:
                climo_values = _climo_wind(config, stid)
            except BaseException as e:
                print('verification warning: problem reading climo data')
                print("*** Reason: '%s'" % str(e))
        if use_cf6:
            try:
                cf6_values = _cf6_wind(config, stid)
            except BaseException as e:
                print('verification warning: problem reading CF6 files')
                print("*** Reason: '%s'" % str(e))
        climo_values.update(cf6_values)  # CF6 overrides
        count_rows = 0
        for index, row in obs_daily.iterrows():
            date = row[datename]
            if date in climo_values.keys():
                count_rows += 1
                obs_wind = row['wind_speed']
                cf6_wind = climo_values[date]['wind']
                if obs_wind - cf6_wind >= 5:
                    if config['debug'] > 9:
                        print('verification warning: obs wind for %s (%0.0f) much larger than '
                              'cf6/climo wind (%0.0f); using obs' % (date, obs_wind, cf6_wind))
                else:
                    obs_daily.loc[index, 'wind_speed'] = cf6_wind
        if config['debug'] > 9:
            print('verification: found %d matching rows for wind' % count_rows)

    # Round values to nearest degree, knot, and centi-inch
    round_dict = {'wind_speed': 0}
    if 'air_temp_high_6_hour' in vars_request:
        round_dict['air_temp_high_6_hour'] = 0
    if 'air_temp_low_6_hour' in vars_request:
        round_dict['air_temp_low_6_hour'] = 0
    round_dict['air_temp_max'] = 0
    round_dict['air_temp_min'] = 0
    if 'precip_accum_six_hour' in vars_request:
        round_dict['precip_accum_six_hour'] = 2
    round_dict['precip_accum_one_hour'] = 2
    obs_daily = obs_daily.round(round_dict)

    # Lastly, place all the values we found into a list of Daily objects. Rename the columns and then iterate over rows.
    if 'air_temp_high_6_hour' in vars_request:
        obs_daily.rename(columns={'air_temp_high_6_hour': 'high'}, inplace=True)
    else:
        obs_daily.rename(columns={'air_temp_max': 'high'}, inplace=True)
    if 'air_temp_low_6_hour' in vars_request:
        obs_daily.rename(columns={'air_temp_low_6_hour': 'low'}, inplace=True)
    else:
        obs_daily.rename(columns={'air_temp_min': 'low'}, inplace=True)
    if 'precip_accum_six_hour' in vars_request:
        obs_daily.rename(columns={'precip_accum_six_hour': 'rain'}, inplace=True)
    else:
        obs_daily.rename(columns={'precip_accum_one_hour': 'rain'}, inplace=True)
    obs_daily.rename(columns={'wind_speed': 'wind'}, inplace=True)

    # Make sure rain has no missing values rather than zeros. Groupby appropriately dealt with missing values earlier.
    obs_daily['rain'].fillna(0.0, inplace=True)
    # Set datetime as the index. This will help use datetime in the creation of the Dailys.
    obs_daily = obs_daily.set_index(datename)
    # Remove extraneous columns
    export_cols = ['high', 'low', 'wind', 'rain']
    for col in obs_daily.columns:
        if col not in export_cols:
            obs_daily.drop(col, axis=1, inplace=True)

    # Create list of Daily objects
    dailys = []
    if config['debug'] > 50:
        print('verification: here are the values')
    for index, row in obs_daily.iterrows():
        date = index.to_pydatetime()
        daily = Daily(stid, date)
        for attr in export_cols:
            setattr(daily, attr, row[attr])
        if config['debug'] > 50:
            print('%s %0.0f/%0.0f/%0.0f/%0.2f' % (daily.date, daily.high, daily.low, daily.wind, daily.rain))
        dailys.append(daily)

    return dailys


def main(config, stid):
    """
    Retrieves yesterday and today's verification.

    We need to be careful about what the starting date is. If it is an incomplete verification day, then that incomplete
    data will overwrite the previous day's verification. It is important, however, to make sure that we get the final
    values for yesterday. Therefore, let's make sure it starts at 6Z yesterday.
    """

    # Get dates
    end_date = datetime.utcnow()
    yesterday = end_date - timedelta(hours=24)
    start_date = datetime(yesterday.year, yesterday.month, yesterday.day, 6)
    start, end = meso_api_dates(start_date, end_date)

    # Download latest CF6 files. There's no need to do this all the time
    if 12 <= end_date.hour < 20:
        # If we're at the beginning of the month, get the last month too
        if end_date.day < 3:
            num_files = 2
        else:
            num_files = 1
        get_cf6_files(config, stid, num_files)

    # Get the daily verification
    dailys = get_verification(config, stid, start, end)

    return dailys


def historical(config, stid, start_date):
    """
    Retrieves historical verifications starting at start (datetime). Sets the hour of start to 6, so that we don't get
    incomplete verifications.
    """

    # Get dates
    start_date = start_date.replace(hour=6)
    end_date = datetime.utcnow()
    start, end = meso_api_dates(start_date, end_date)

    # Download CF6 files
    get_cf6_files(config, stid, 12)

    # Get the daily verification
    dailys = get_verification(config, stid, start, end, use_climo=True)

    return dailys
