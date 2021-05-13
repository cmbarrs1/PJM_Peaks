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
from sms_email import sendtxt

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
    sendtxt('PJM Peaks Crash', error_msg)
    logging.critical(error_msg)

def file_check(file_path):
    """Check if file exists on system"""
    if path.exists(file_path):
        return True
    else:
        return False

def human_readable_time(mills):
    """Convert mills to human readable"""
    dt_obj=datetime.fromtimestamp(float(mills)/1000)
    return dt_obj.strftime("%Y-%m-%d, %I:%M %p")

def prelim_loads(file_path):
    """Build first load file on new installation"""
	#{PJM : {time: load}}
    init_peak_loads={}
    init_peak_loads = {'PJM RTO Total' : {1:1, 2:2, 3:3, 4:4, 5:5},
                        'COMED Zone': {1:1, 2:2, 3:3, 4:4, 5:5}}
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
    cur_time=load_data[cur_index]['Time']	#current time in mills
    dt_obj=datetime.fromtimestamp(float(cur_time)/1000) #convert mills to datetime object
    cur_minutes = dt_obj.minute #extract minutes
    look_back = int(cur_minutes/5) #how many steps to look back
    temp_loads=[]
    if cur_minutes >= 5:
        for x in range (cur_index-look_back,cur_index):
            temp_loads.append(float(load_data[x][RTO]))
    else:
        _logger.debug(float(load_data[cur_index][RTO]))
        temp_loads.append(float(load_data[cur_index][RTO]))
    _logger.debug('Current Minute: %s', cur_minutes)
    _logger.debug(temp_loads)
    return max(temp_loads)

def cur_hour(mills):
    """change mills to current hour xx:00 (in mills)"""
    dt_obj=datetime.fromtimestamp(float(mills)/1000) #convert mills to datetime object
    new_dt_obj=dt_obj.replace(minute=0, second=0, microsecond=0)
    return new_dt_obj.timestamp()*1000

def cur_min(mills):
    """Get current minute"""
    dt_obj=datetime.fromtimestamp(float(mills)/1000) #convert mills to datetime object
    return dt_obj.minute #extract minutes


def peak_load_cleanup(RTO, peak_dict, load_data):
    """clean up the peak load file"""
    last_time=load_data[len(load_data)-1]['Time']
    dt_obj=datetime.fromtimestamp(float(last_time)/1000) #convert mills to datetime object
    new_dt_obj=dt_obj.replace(minute=0, second=0, microsecond=0)
    last_time_on_hour=new_dt_obj.timestamp()*1000 #Current hour, last full hour will be less then this number
    times=map(cur_hour, list(peak_loads[RTO].keys())) #change list to on the hour
	#https://stackoverflow.com/questions/34569966/remove-duplicates-in-python-list-but-remember-the-index
    unique_times=set()
    remove_index=[] #index of doubles that need to be removed
    for i, elem in enumerate(times):
        if elem not in unique_times:
            pass
        else:
            remove_index.append(i)
            unique_times.add(elem)
        if len(remove_index)>0: #If there are doubles remove
            dict_keys=list(peak_loads[RTO].keys()) #get a list of dict keys
            for item in remove_index:
                peak_dict[RTO].pop([dict_keys[item]]) #remove the dict keys based on index determined above.
    return peak_dict

def prediction_algorithm(RTO, load_data, peak_loads, multiplier, peak_file_path):
    """heart of the program"""
    for x in range(13, len(load_data)): #start a 13 to miss header and have 1hr of data
        _logger.debug('prediction_algorithm iteration %s: of %s', x, len(load_data)-1)
        _logger.debug('Iteration Time: %s', human_readable_time(load_data[x]['Time']))
        _logger.debug('Peak Loads: %s', peak_loads)
        if cur_min(load_data[x]['Time'])<5: #every hour clean up peak loads file
            peak_load_cleanup(RTO, peak_loads, load_data)
        gen_slope=generation_slope(float(load_data[x][RTO]),float(load_data[x-12][RTO]),12)
        if gen_slope>0: #Do not do predictions on decreasing loads
			#Waring Prediction
            predicted_max=(multiplier*gen_slope)*12+float(load_data[x][RTO])
            if predicted_max > min(list(peak_loads[RTO].values())): #at the current load growth will be a peak in next hour
                _logger.info('Peak Warning')
                if x == len(load_data)-1: #check if latest iteration
                    msg = RTO + ' ' + float(load_data[x][RTO]) + 'MW @ ' + human_readable_time(load_data[x]['Time'])
                    sendtxt('Peak Warning', msg)
                    #here will will send text or dow whatever
                status={'status' : 'WARNING', 'RTO': RTO}
                cur_max = true_max_load(RTO, load_data, x) #get max load in the current hour
                if not (cur_max in list(peak_loads[RTO].values())): #check if current load is in list
                        peaks=list(peak_loads[RTO].values())
                        _logger.debug('Current Peaks: %s',peaks)
                        times=list(peak_loads[RTO].keys())
                        for y in range(0,4): #loop through peaks to see if new max load is a peak
                            if cur_max > peaks[y]:
                                _logger.info('Peak')
                                if x == len(load_data)-1: #check if latest iteration
                                    pass
                                    #here will will send text or dow whatever
                                peaks.insert(y,cur_max)
                                _logger.debug('Peaks after insert %s', peaks)
                                times.insert(y,float(load_data[x]['Time']))
                                temp_dict={}
                                for z in range(0, 5):
                                    temp_dict[times[z]]=peaks[z]
                                    peak_loads[RTO]=temp_dict
                                    _logger.debug('Before Writing: %s', peak_loads)
                                    write_json_file(peak_loads, peak_file_path)
                                break #as not to fill all subsequent loads with data

if __name__=="__main__":
    sys.excepthook = my_exception_hook #Catches all expections not in try/except
    if 'DEBUG' in sys.argv:
        logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s | %(name)s | %(levelname)s | %(message)s')
        logging.debug('Debug Mode Active')
        logging.debug(sys.argv)
    if 'DEBUG' not in sys.argv:
        logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
                        filename='/home/chris/python_scripts/production/logs/main_log.log',
                        filemode='a')

    lookback_raw=(list(filter(lambda x: '--lookback' in x, sys.argv)))#check if --lookback is in sys.argv
    if lookback_raw: #if lookback_raw has elements, will evaluate as true
        lookback_raw_str=lookback_raw[0]
        lookback=int((lookback_raw_str.split('=')[1]))
    else:
        lookback = 0#look back how far in 5min increments, either 0 or 13+, 0 is look at whole file

    peak_load_file ='/home/chris/python_scripts/production/data/Peak_Loads.json'
    load_data_file ='/home/chris/python_scripts/production/data/PjmCurrentLoads.csv'
    status_file='/home/chris/python_scripts/production/data/Peak_Status.json'
    SLOPE_MULTIPLIER = 1.03

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
    peak_loads=peak_load_cleanup('PJM RTO Total',peak_loads,load_data)
    peak_loads=peak_load_cleanup('COMED Zone',peak_loads,load_data)
    prediction_algorithm('PJM RTO Total', load_data, peak_loads, SLOPE_MULTIPLIER,peak_load_file)
    prediction_algorithm('COMED Zone', load_data, peak_loads, SLOPE_MULTIPLIER,peak_load_file)
