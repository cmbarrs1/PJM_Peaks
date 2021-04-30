#!/usr/bin/python3
"""This program is to predict the peaks of the PJM and 
COMED RTO for purposes of reducting capacity charge"""

import sys
import traceback
import logging
from os import path
import json
from csv import DictReader
from csv import DictWriter
from datetime import datetime

_logger = logging.getLogger(__name__)

def my_exception_hook(exp_type, value, tba):
    """
    Intended to be assigned to sys.exception as a hook.
    Gives programmer opportunity to do something useful with info from uncaught exceptions.

    Parameters
    exp_type: Exception type
    value: Exception's value
    tba: Exception's traceback
    """

    # NOTE: because format() is returning a list of string,
    # I'm going to join them into a single string, separating each with a new line
    traceback_details = '\n'.join(traceback.extract_tb(tba).format())

    error_msg = "An exception has been raised outside of a try/except!!!\n" \
                f"Type: {exp_type}\n" \
                f"Value: {value}\n" \
                f"Traceback: {traceback_details}"
    logging.critical(error_msg)

def file_check(file_path):
    """Check if file exists on system"""
    if path.exists(file_path):
        return True
    else:
        return False

def prelim_loads(file_path):
    """Build first load file on new installation"""
	#{PJM : {time: load}}
    init_peak_loads={}
    init_peak_loads = {'PJM' : {1:1, 2:2, 3:3, 4:4, 5:5},
                        'COMED': {1:1, 2:2, 3:3, 4:4, 5:5}}
    with open(file_path, 'w') as outfile:
        json.dump(init_peak_loads, outfile, indent=4)

def write_json_file(data, file_path):
    """Write basic dictionary to file"""
    with open(file_path, 'w') as outfile:
        json.dump(data, outfile, indent=4)

def prelim_status(file_path):
    """Build Status file on new installation"""
    status={}
    status={'status' : 'NORMAL',
		'RTO' : 'NONE'}
    with open(file_path, 'w') as outfile:
        json.dump(status, outfile, indent=4)

def import_basic_json(file_path):
    """import basic json file to dictionary"""
    with open(file_path, 'r') as infile:
        data=json.load(infile)
    return data

def import_load_data(data_file, x_lines=0):
    """Read in load data, x_lines is the last X lines in file
		if no x_lines is given whole file will be read in"""
    with open(data_file, 'r') as read_obj:
        csv_dict_reader = DictReader(read_obj)
    if x_lines==0:
        all_loads=list(csv_dict_reader)
    else:
        all_loads=list(csv_dict_reader)[-x_lines:]
    return all_loads

def generation_slope(current_load, beginning_load, look_back):
    """determine generation slope, if less than 0 change to 0"""
    slope=(current_load - beginning_load)/look_back
    if slope < 0:
        slope = 0
    return slope 

def true_max_load(RTO, load_data, cur_index):
    """Gets the max for the current hour"""
    cur_time=load_data[x]['Time']	#current time in mills
    dt_obj=datetime.fromtimestamp(float(cur_time)/1000) #convert mills to datetime object
    cur_minutes = dt_obj.minute #extract minutes
    look_back = int(cur_minutes/5) #how many steps to look back
    temp_loads=[]
    for x in range (cur_index-look_back,cur_index):
        temp_loads.append(float(load_data[x][RTO]))
    return max(temp_loads)

def cur_hour(mills):
    """change mills to current hour xx:00 (in mills)"""
    dt_obj=datetime.fromtimestamp(float(mills)/1000) #convert mills to datetime object
    new_dt_obj=dt_obj.replace(minute=0, second=0, microsecond=0)
    return new_dt_obj.timestamp()*1000

def peak_load_cleanup(RTO, peak_dict, load_data):
    """clean up the peak load file"""
    last_time=load_data[len(load_data)]['Time']
    dt_obj=datetime.fromtimestamp(float(last_time)/1000) #convert mills to datetime object
    new_dt_obj=dt_obj.replace(minute=0, second=0, microsecond=0)
    last_time_on_hour=new_dt_obj.timestamp()*1000 #Current hour, last full hour will be less then this number
    times=map(cur_hours, list(peak_loads[RTO].keys())) #change list to on the hour
	#https://stackoverflow.com/questions/34569966/remove-duplicates-in-python-list-but-remember-the-index
    unique_times=set()
    remove_index=[] #index of doubles that need to be removed
    for i, elem in enumerate(times):
        if elem not in seen:
            pass
        else:
            remove_index.append(i)
            seen.add(elem)
        if len(remove_index)>0: #If there are doubles remove
            dict_keys=list(peak_loads[RTO].keys()) #get a list of dict keys
            for item in remove_index:
                peak_dict[RTO].pop([dict_keys[item]]) #remove the dict keys based on index determined above.
    return peak_dict

def prediction_algorithm(RTO, load_data, peak_loads, multiplier, peak_file_path):
    """heart of the program"""
    for x in range(13, len(load_data)): #start a 13 to miss header and have 1hr of data
        gen_slope=generation_slope(float(load_data[x][RTO]),float(load_data[x-12][RTO]),12)
        if gen_slope>0: #Do not do predictions on decreasing loads
			#Waring Prediction
            predicted_max=(multipler*gen_slope)*12+float(load_data[x][RTO])
            if predicted_max > min(list(peak_loads[RTO].values())): #at the current load growth will be a peak in next hour
                _logger.info('Peak Warning')
                status={'status' : 'WARNING', 'RTO': RTO}
		#Actual Peak Logging (should really be checking time, not load to see if current peak is in list)
                cur_max = true_max_load(RTO, load_data, x) #get max load in the current hour
                if not (cur_max in list(peak_loads[RTO].values())): #check if current load is in list
                        peaks=list(peak_loads[RTO].values())
                        times=list(peak_loads[RTO].keys())
                        for y in range(0,4): #loop through peaks to see if new max load is a peak
                            if cur_max > peaks[y]:
                                _logger.info('Peak')
                                peaks.insert(y,cur_max)
                                times.insert(y,float(load_data[x]['Time']))
                                temp_dict={}
                                for z in range(0, len(peaks)):
                                    temp_dict[times[z]]=peaks[z]
                                    peaks[RTO]=temp_dict
                                    write_json_file(peaks, peak_file_path)
                                    break #break for loop to not fill up rest of of list with data

if __name__=="__main__":
    sys.excepthook = my_exception_hook #Catches all expections not in try/except
    if 'DEBUG' in sys.argv:
        logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s | %(name)s | %(levelname)s | %(message)s')
        logging.debug('Debug Mode Active')
    if 'DEBUG' not in sys.argv:
        logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
                        filename='/home/chris/python_scripts/production/logs/main_log.log',
                        filemode='a')

    peak_load_file ='/home/chris/python_scripts/production/data/Peak_Loads.json'
    load_data_file ='/home/chris/python_scripts/production/data/PjmCurrentLoads.csv'
    status_file='/home/chris/python_scripts/production/data/Peak_Status.json'
    SLOPE_MULTIPLIER = 1.03
    lookback = 0 #look back how far in 5min increments, either 0 or 13+, 0 is look at whole file

    if not file_check(peak_load_file): #check if peak load file exists, if not create file
        prelim_loads(peak_load_file) #create new load file
    peak_loads=import_basic_json(peak_load_file) #import peak load file
    if not file_check(status_file): #check if status file exists, if not create file
        prelim_status(status_file) #create new status file
    current_status=import_basic_json(status_file) #import status file
    load_data=import_load_data(load_data_file, lookback) #import loads into dictionary
    ####START PREDICTION ALGORITHM########
    if len(load_data) < lookback:
        _logger.critical('Lookback larger then dataset, Exiting')
        raise SystemExit
    peak_loads=peak_load_cleanup('PMJ RTO Total',peak_loads,load_data)
    peak_loads=peak_load_cleanup('COMED',peak_loads,load_data)
    prediction_algorithm('PMJ RTO Total', load_data, peak_loads, SLOPE_MULTIPLIER,peak_load_file)
    prediction_algorithm('COMED', load_data, peak_loads, SLOPE_MULTIPLIER,peak_load_file)
