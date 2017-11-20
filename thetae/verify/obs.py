#
# Copyright (c) 2017 Jonathan Weyn <jweyn@uw.edu>
#
# See the file LICENSE for your rights.
#

'''
Retrieve observations from MesoWest.
'''

from MesoPy import Meso
import pandas as pd
import numpy as np
from thetae.util import _meso_api_dates, _date_to_string, TimeSeries
from datetime import datetime, timedelta

def _cloud(series):
    '''
    Changes the cloud code to a fractional converage.
    '''
    translator = { 1 : 0.,
                   2 : 50.,
                   3 : 75.,
                   4 : 100.,
                   6 : 25.
                   }
    new_series = series.copy()
    for index, value in series.iteritems():
        try:
            new_value = translator[int(value % 10.)]
        except:
            new_value = 0.0
        new_series.loc[index] = new_value
    return new_series

def _reformat_date(series):
    '''
    Reformats the pandas string date format in a MesoWest series
    '''
    new_series = series.copy()
    for index, date in series.iteritems():
        new_date = _date_to_string(datetime.strptime(date, '%Y-%m-%dT%H:%M:%SZ'))
        new_series.loc[index] = new_date
    return new_series

def get_obs(config, stid, start, end):
    '''
    Retrieve data from MesoPy
    '''
    
    # MesoWest token and init
    meso_token = config['Verify']['api_key']
    m = Meso(token=meso_token)
    if int(config['debug']) > 9:
        print('obs: MesoPy initialized for station %s' % stid)

    # Look for desired variables
    vars_request = ['air_temp', 'dew_point_temperature', 'wind_speed',
                    'wind_direction', 'cloud_layer_1_code',
                    'cloud_layer_2_code', 'cloud_layer_3_code',
                    'precip_accum_one_hour', 'weather_condition']
    
    # Add variables to the api request
    vars_api = ''
    for var in vars_request:
        vars_api += var + ','
    vars_api = vars_api[:-1]
    
    # Units
    units = 'temp|f,precip|in,speed|kts'

    # Retrieve data
    print('obs: retrieving data from %s to %s...' % (start, end))
    obs = m.timeseries(stid=stid, start=start, end=end, vars=vars_api,
                       units=units, hfmetars='0')
    obspd = pd.DataFrame.from_dict(obs['STATION'][0]['OBSERVATIONS'])
    
    # Rename columns to requested vars. This changes the columns in the
    # DataFrame to corresponding names in vars_request, because otherwise the
    # columns returned by MesoPy are weird.
    obs_var_names = obs['STATION'][0]['SENSOR_VARIABLES']
    obs_var_keys  = list(obs_var_names.keys())
    col_names = list(map(''.join, obspd.columns.values))
    for c in range(len(col_names)):
        col = col_names[c]
        for k in range(len(obs_var_keys)):
            key = obs_var_keys[k]
            if col == list(obs_var_names[key].keys())[0]:
                col_names[c] = key
    obspd.columns = col_names
    datename = 'DATETIME'
    obspd = obspd.rename(columns={'date_time' : datename})

    # Let's add a check here to make sure that we do indeed have all of the
    # variables we want
    for var in vars_request:
        if var not in col_names:
            obspd[var] = np.nan
    
    # Reformat data into hourly obs
    # Find mode of minute data: where the hourly metars are. Sometimes there are
    # additional obs at odd times that would mess with rain totals.
    minutes = []
    for row in obspd.iterrows():
        date = row[1][datename]
        minutes.append(pd.to_datetime(date).minute) # convert pd str to dt
    minute_count = np.bincount(np.array(minutes))
    rev_count = minute_count[::-1]
    minute_mode = minute_count.size - rev_count.argmax() - 1
    if int(config['debug']) > 9:
        print('obs: mode of hourly data is minute %d' % minute_mode)
    # Subset only hourly data
    obs_hourly = obspd[pd.DatetimeIndex(obspd[datename]).minute == minute_mode]

    # Check for all requested variables, otherwise set them to null, or 0
    # for precipitation, or 1.0 for cloud layers
    for var in vars_request:
        if not(var in col_names):
            obs_hourly[var] = np.nan
    obs_hourly['precip_accum_one_hour'].fillna(0.0, inplace=True)
    obs_hourly['cloud_layer_1_code'].fillna(1.0, inplace=True)
    obs_hourly['cloud_layer_2_code'].fillna(1.0, inplace=True)
    obs_hourly['cloud_layer_3_code'].fillna(1.0, inplace=True)

    # Format cloud data
    cloud = (_cloud(obspd['cloud_layer_1_code']) +
             _cloud(obspd['cloud_layer_2_code']) +
             _cloud(obspd['cloud_layer_3_code']))
    # Cloud exceeding 100% set to 100
    cloud[cloud > 100.] = 100.
    # Drop old cloud columns and replace with only total cloud
    obs_hourly = obs_hourly.drop('cloud_layer_1_code', axis=1)
    obs_hourly = obs_hourly.drop('cloud_layer_2_code', axis=1)
    obs_hourly = obs_hourly.drop('cloud_layer_3_code', axis=1)
    obs_hourly['cloud'] = cloud

    # Reformat dates, replacing pandas default string format with SQL format
    new_dates = _reformat_date(obs_hourly[datename])
    obs_hourly = obs_hourly.drop(datename, axis=1)
    obs_hourly[datename] = new_dates
    if int(config['debug']) > 50:
        print('obs: here is the timeseries')
        print(obs_hourly)

    # Rename columns to match default schema
    rename_dict = {
                    'air_temp' : 'temperature',
                    'dew_point_temperature' : 'dewpoint',
                    'wind_speed' : 'windSpeed',
                    'wind_direction' : 'windDirection',
                    'precip_accum_one_hour' : 'rainHour',
                    'weather_condition' : 'condition'
                    }
    obs_hourly = obs_hourly.rename(columns=rename_dict)
    
    # Generate TimeSeries object
    timeseries = TimeSeries(stid)
    timeseries.data = obs_hourly
    
    return timeseries


def main(config, stid):
    '''
    Retrieves the latest 24 hours of observations at site stid.
    '''
    
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(hours=24)
    start, end = _meso_api_dates(start_date, end_date)
    
    timeseries = get_obs(config, stid, start, end)

    return timeseries

def historical(config, stid, start_date):
    '''
    Retrieves observations at site stid starting at start_date.
    '''
    
    end_date = datetime.utcnow()
    start, end = _meso_api_dates(start_date, end_date)
    
    timeseries = get_obs(config, stid, start, end)

    return timeseries