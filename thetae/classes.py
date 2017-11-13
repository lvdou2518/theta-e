#
# Copyright (c) 2017 Jonathan Weyn <jweyn@uw.edu>
#
# See the file LICENSE for your rights.
#

'''
Define classes for thetae.
'''

# =============================================================================
# Classes
# =============================================================================

import numpy as np
import pandas as pd

class TimeSeries():
    def __init__(self):
        self.data = pd.DataFrame()

class Daily():
    def __init__(self):
        self.high = np.nan
        self.low = np.nan
        self.wind = np.nan
        self.rain = np.nan

class Forecast(stid, date, source):
    '''
        Forecast object for a single date. Contains both a timeseries and daily values.
        '''
    
    def __init__(self):
        self.stid = stid
        self.source = source
        self.date = date
        self.timeseries = TimeSeries()
        self.daily = Daily()
