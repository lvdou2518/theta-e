#
# Copyright (c) 2017 Jonathan Weyn <jweyn@uw.edu>
#
# See the file LICENSE for your rights.
#

'''
Main engine for the theta-e system.
'''

import thetae.db

# Step 1: check the database
# Step 2: if database has no table for the stid or data are old, reset the table
# Step 3: if applicable, run db_init for site: retrieves historical
#   We may need to write a separate script to initialize a new model
# Step 4: retrieve forecast data; save to db
# Step 5: retrieve verification data; save to db
# Step 6: run manager to calculate verification statistics; save to db
# Step 7: run plotting scripts; theta-e website scripts

from . import getConfig, Forecast

def main(options, args):
    '''
    Main engine process.
    '''
    
    config = getConfig(args[0])
    print(config)

    # Step one: check the database initialization
    add_sites = thetae.db.db_init(config)
    print(add_sites)

def mainArchive(config):
    return
