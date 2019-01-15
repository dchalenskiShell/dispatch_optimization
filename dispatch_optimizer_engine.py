# -*- coding: utf-8 -*-
"""
Created on Sun Nov 18 15:40:52 2018

@author: David.Chalenski

2018-12-19:
  This is the final version of the DO code which was used for the PoC.
  It is being copied and held here for posterity
  It should be run in the Anaconda environment PoC_fixed_2018_12_14 to ensure appropriate modules


To implement:
  Return to SOC
  DONE: Properly calculate demand charges when PV is curtailed/disabled
  4CP
  Calculate gas cost for genset when it's running (add up energy dispatched and subtract gas cost)
  Delay cost - e.g. put in a cost to doing things later
  ***Implement boolean to ensure battery doesn't charge/discharge simultaneously
  Marginal cost stack to see what the cost of producing each asset is (approach offer curve)
    In general try to visualize what it's doing better, stacked revenue curve?
  Boolean OR 
  
  
This should be run on Env

NOTE: AG needs battery discharge to be +, opposite the convention here
I have implemented battery_sign to flip this below.  This may have knock-on effects
  
  
"""

import pyomo.environ as en
#import read_input
import numpy as np
import matplotlib.pyplot as plt
from shutil import copyfile
import time
import datetime
from timeit import default_timer as timer
import os
import pandas as pd
import broken_barh_plot
#from pyomo.core import Var
#import pprint

plt.close('all')

#====================TESTING PARAMETERS================
#Some of these may need to be nuked when productized
splitPower = True #Do you want to split power into pos and neg?
manipulateLoad = False #Artificially modify Sr load for testing purposes
manipulateLoadValue = 2 #can do, 2, 5, etc.

#====================/TESTING PARAMETERS================

#duration of calculation
start = timer()

createLogfile = True
currFilePath = os.path.dirname(os.path.realpath(__file__))
currFileName = 'battery_schedule_lp_test_v2.py'

#============Input variables===========
SOC_init = 500 #kWh  #WILL COME FROM TONY
SOC_fixed = 840
SOCMin = 200 #kWh
SOCMax = 1050 #kWh
powerBatteryMax = 250 #kW
intervalsPerHour = 4 #e.g. 15-minute intervals = 4 per hour #WILL COME FROM TONY
#Do we need to scale the input PV values because we are using my roof vs STCH MG
PVScale = 5
PVRoundTripEfficiency = 1
gensetHeatRate = 9.8
costGas = 3 #($/MWh)
netInterconnectConstraint = 300 #kW
#Marginal costs are currently used to prioritize these assets
#Higher marginal costs forces that asset to curtail over lower marginal cost assets
#This is currently not figured in to the actual revenue calculations
#They are arbitrary and small so as to have little impact if prices are low
marginalCostBattery = .0002 #Just priority, does not include degradation costs
marginalCostPV = .0001 #PV has the highest priority, lowest marginal cost
marginalCostGenset =  .0003 #This does not account for gas price, just priority
#CostToCharge = 1.5 #
#CostToDischarge = .5 #
batteryDegrades = True #Do you want to figure in battery degradation?
enableBattery = True #from TONY
enablePV = True #from TONY
enablePVCurtail = True #from TONY
enableGenset = True #from TONY
enableLoadBank = True #from TONY
enableSRLoad = True #MAYBE from TONY
enableNetInterconnectConstraint = True 
returnToSOC = True #Need to implement
enableDCM = True #enable demand charge management - Vestigial
#convertPriceInMWtoKW = False
enableMarginalCosts = True
resampleFcastsFiveMins = False
priceSpike = True
priceSpikeAmt = 50 #$/MWh for spike
#Sets all the parameters for the December PoC run
PoC_run = False
runOnVM = False
timeSoCFixed = 178

#Read parameters and forecasts files
if runOnVM:
  fdirFcast = 'E:/Optimization/inputs/'
  fname = 'inputs.pkl'
else:
  fdirFcast = 'C:/Users/David.Chalenski/OneDrive - Shell/Documents/ESIS/Microgrid/dispatch optimization/python/dispatch_optimizer_v2/input/'
  #fname = 'forecast_all_topython_pkl.pkl'  #I used this for a lot of testing
  fname = 'input_poc_sample.pkl'
  #Uncomment below for actual files used during PoC
  #fdirFcast = 'C:/Users/David.Chalenski/OneDrive - Shell/Documents/ESIS/Microgrid/autogrid POC/2018-12-14 PoC files/'
  #fname ='input_spike.pkl'
#fname = 'params_test_pkl.pkl'
#params = read_input.input_params(fname, fdirFcast)

fpath = fdirFcast + fname
fcast = pd.read_pickle(fpath)
#fcast = read_input.input_fcast(fname, fdirFcast)

if resampleFcastsFiveMins:
  fcast = fcast.resample('5Min').ffill()
  intervalsPerHour = 12

"""
#Simulate a price spike?
if priceSpike:
  tmp = datetime.datetime.now() - datetime.timedelta(hours=12)
  now = tmp.time()
  #price.index = pd.to_datetime(df.index)
  time1 = fcast[fcast.index.time <= now][-1:].index
  time2 = fcast[fcast.index.time >= now][:1].index
  fcast.loc[time1,'fc_rt_price'] = priceSpikeAmt
  fcast.loc[time2,'fc_rt_price'] = priceSpikeAmt
"""
#=============/Input Variables=============
battery_sign = 1 #AG reads positive as DISCHARGE, so need to flip sign if generating plan for them

dirLogsOut = currFilePath + '\\logs\\' #will come from TONY - log files
dirPlanOut = currFilePath + '\\logs\\'

epochTime = int(np.round(time.time(),0)) #will come from Tony

if not enableMarginalCosts:
  marginalCostBattery = marginalCostPV = marginalCostGenset = 0

#overwrite important parameters for PoC
if PoC_run:
  #CostToDischarge = .5 #
  batteryDegrades = True #Do you want to figure in battery degradation?
  enableBattery = True
  enablePV = False
  enablePVCurtail = False
  enableGenset = False
  enableLoadBank = False 
  enableSRLoad = True 
  enableNetInterconnectConstraint = True
  enableMarginalCosts = True
  netInterconnectConstraint = 200 #kW
  manipulateLoad = False
  PVScale = 1
  battery_sign = -1
  priceSpike = False
  
  createLogfile = True
  if runOnVM:
    currFilePath = 'E:/Optimization/' #Don't actually use this on VM, keep here so defined
    currFileName = 'battery_schedule_lp_test_v2.py'
    dirLogsOut = 'E:/Optimization/logs/' #where to write the output plan
    dirPlanOut = 'E:/Optimization/outputs/'
  else:
    currFilePath = os.path.dirname(os.path.realpath(__file__))
    currFileName = 'battery_schedule_lp_test_v2.py'
  intervalsPerHour = 12
  resampleFcastsFiveMins = False
 
  now = datetime.datetime.now()
  dateToday = now.strftime("%Y-%m-%d")
  rngPoC = pd.date_range(str(dateToday) + ' 06:00:00', periods= len(fcast), freq='5Min') #Add 6 to get time to UTC
  fcast = fcast.set_index( rngPoC )

#Convert price input DatFrame to pyomo-readable dict
price = fcast['fc_rt_price'].copy()

"""
#Simulate a price spike?
if priceSpike:
  tmp = datetime.datetime.now() - datetime.timedelta(hours=12)
  now = tmp.time()
  #price.index = pd.to_datetime(df.index)
  time1 = price[price.index.time <= now][-1:].index
  time2 = price[price.index.time >= now][:1].index
  price.loc[time1] = priceSpikeAmt
  price.loc[time2] = priceSpikeAmt
"""

if not PoC_run:
  #Setup test forecast cases
  if False:
    #Test prices at 0 except 2-hour period in middle of day
    price.iloc[:] = 0
    price.iloc[1:5] = 100
    price.iloc[ 51:75 ] = 50
  elif False:
    #Linearly increasing price
    price.iloc[:] = np.arange( len(fcast ) )
  elif False:
    #Response to negative prices
    price.iloc[:] = 1
    price.iloc[ 51:75 ] = -50
  elif False:
    #Respond to positive and negative prices
    price.iloc[:] = 5
    price.iloc[ 21:36 ] = -50 
    price.iloc[ 51:70 ] = 50
  elif False:
    #Respond to positive and negative prices
    price.iloc[:] = 1
    price.iloc[ 21:36 ] = 50 
    price.iloc[ 51:70 ] = -50
  elif False:
    #constant price throughout period
    price.iloc[:] = 50
  elif False:
    #Respond to positive and negative prices
    price.iloc[:] = 5
    price.iloc[ 15:25 ] = -50 
    price.iloc[ 51:71 ] = 45
    price.iloc[ 71:80 ] = 50

#powerLoadBank = fcast['fc_solar_kw'].copy()

#=====================Integrate enable/disable logic=============
if enableGenset:
  powerGensetMax = 125 #kW, always use positive
else:
  powerGensetMax = 0 #kW
if enableLoadBank:
  powerLoadBankMax = 245 #KVA, but assume kW, actually 250 but shift from battery for plotting
else:
  powerLoadBankMax = 0
#=====================/Integrate enable/disable logic=============

#=============Battery degradation estimation===========
#This is a rough estimator for figuring in degradation of battery costs
#assumes a fixed reduction and future value of 
#Assume following numbers:
if batteryDegrades:
  capacityRetained = 0.7 #% of capacity remaining after X years
  numYearsLife = 10 #Number of years at which above capacity remains
  numHoursLife = numYearsLife * 365 * 24 #hours
  capacityInitial = 4.5 #MWh, used DH numbers
  capexPerMWh = 5000000 * 0.3 / capacityInitial #USD, assume 30% of capex is chemistry, used DH numbers
  costDegradationTotal = capexPerMWh * (1 - capacityRetained) #capex lost to degradation
  degradationCostPerMWHour = costDegradationTotal / numHoursLife #$ per MWh
  degradationCostSlope = degradationCostPerMWHour * (powerBatteryMax / 1000) #$ per hour at peak power
  print('cost of battery degradation used : $' + str(np.round(degradationCostPerMWHour,2)) + '$/MWh')
  
else:
  degradationCostSlope = 0 #Use if you don't want battery to degrade
#=============/Battery degradation estimation===========

#============Manipulate  inputs=======================
price.index = np.arange( len(fcast) )
priceDict = price.to_dict()
#Read in load data
#Convert load input DataFrame to pyomo-readable dict
loadSR = fcast['fc_load_SR'].copy()
if manipulateLoad:
  loadSR.iloc[25:65] *= manipulateLoadValue
if not enableSRLoad:
  loadSR.iloc[:] = 0
loadSR.index = np.arange( len(fcast) )
loadSRDict = loadSR.to_dict()
#Read in forecast of solar PV in KW
#Note: PV is export, so power is negative
fcastPV = fcast['fc_solar_kw'].copy() *-1 * PVScale
if not enablePV:
  fcastPV[:] = 0
fcastPV.index = np.arange( len(fcast) )
#Zero out PV where price forecasted to be negative
if enablePVCurtail:
  fcastPV = fcastPV * (price >= 0)
fcastPVDict = fcastPV.to_dict()




#Create variable for PV - SR load
#If positive, PV > SR and export
deltaPVSR = fcastPV - loadSR
#deltaPVSRDict = deltaPVSR.to_dict()
deltaPVSRPos = deltaPVSR.copy()
deltaPVSRNeg = deltaPVSR.copy()
for i, a in enumerate(deltaPVSR):
  if a>=0:
    deltaPVSRNeg[i] = 0
  else:
    deltaPVSRPos[i] = 0
deltaPVSRPosDict = deltaPVSRPos.to_dict()
deltaPVSRNegDict = deltaPVSRNeg.to_dict()




#============/Manipulate  inputs=======================

#Initialize Model
m = en.ConcreteModel()
  
#SETS
#RangeSet: start, end, step
#keep Python ordering by starting at 0
m.T = en.RangeSet(0, len(priceDict) - 1 )
"""
def d(m):
  return np.arange(96)
m.T = en.Set(initialize = d)
"""
# PARAMETERS
# # Real Time Price forecast, time t
m.price = en.Param(m.T, within = en.Reals, initialize = priceDict)
m.loadSR = en.Param(m.T, within = en.NonNegativeReals, initialize = loadSRDict)
m.fcastPV = en.Param(m.T, within = en.Reals, initialize = fcastPVDict)
m.deltaPVSRPos = en.Param(m.T, within = en.Reals , initialize = deltaPVSRPosDict)
m.deltaPVSRNeg = en.Param(m.T, within = en.Reals , initialize = deltaPVSRNegDict)
  
#VARIABLES
#Discharge power (note this is obviously instantaneous, not scaled for 15 minute interval)
#Initialize most to 0 so final iteration remains finite
m.powerBattery = en.Var( m.T, bounds=(-powerBatteryMax, powerBatteryMax), initialize = 0 )
m.SOC = en.Var(m.T, bounds=(SOCMin, SOCMax) ) 
m.powerBatteryPos = en.Var( m.T, bounds=(0, powerBatteryMax), initialize = 0 )
m.powerBatteryNeg = en.Var( m.T, bounds=(-powerBatteryMax, 0), initialize = 0 )
m.powerLoadBank = en.Var( m.T, bounds=( 0 , powerLoadBankMax ), initialize = 0 )
if enablePVCurtail:
  m.booleanPV = en.Var( m.T, within = en.Boolean , initialize = enablePV )
else:
  m.booleanPV = en.Var( m.T, bounds = (True , True) , initialize = enablePV )
m.powerGenset = en.Var( m.T, bounds=( -powerGensetMax, 0 ), initialize = 0 )
m.powerImport = en.Var( m.T, initialize = 0 )
m.powerExport = en.Var( m.T, initialize = 0 ) #IS THERE WHERE WE WANT TO IMPOSE EXPORT CONSTRAINT???

#if enablePV:
#  m.powerPV = en.Var( m.T, bounds=(0, powerPVMax), initialize = fcastPVDict )  #REALLLYYYY??????????
#else:
#  m.powerPV = en.Var( m.T, bounds=(0, powerPVMax), initialize = 0 )



#OBJECTIVE STATEMENT
"""things this may not do yet:
degradation cost
turn PV off
return to SOC
"""
def Total_cost(model):
  #Battery Charge + Battery Discharge + Load Bank + PV full/0
  #Note all powers + mean importing (buying/charging/consuming)
  return sum(   \
      ( m.powerImport[t] + m.powerExport[t] ) * m.price[t] \
      + ( m.powerBatteryPos[t] * degradationCostSlope * enableBattery ) \
      - ( m.powerBatteryNeg[t] * degradationCostSlope * enableBattery )
      for t in m.T)
#      ( ( m.powerBatteryPos[t] - deltaPVSRPos[t] * enableDCM ) * m.price[t] + ( m.powerBatteryPos[t] * degradationCostSlope ) ) + \
#      ( ( m.powerBatteryNeg[t] - deltaPVSRNeg[t] * enableDCM ) * m.price[t] - ( m.powerBatteryNeg[t] * degradationCostSlope ) ) + \
#      ( m.powerLoadBank[t] * m.price[t] ) + \
#      ( m.booleanPV[t] * -m.price[t] ) \
#      for t in m.T)  #Note: +ve power = charge/consume/import (EE convention)
m.OBJ = en.Objective(rule=Total_cost, sense = en.minimize)


#CONSTRAINTS
# State of charge of the baterry
def State(m, t):
    if t == 0:
        return m.SOC[t] == SOC_init   #Initialize at 50% SOC  #100 + m.powerBattery[t]  
#    #broken below - need to go backwards in time
#    if t == timeSoCFixed:
#        return m.SOC[t] == SOC_fixed   #Initialize at 50% SOC  #100 + m.powerBattery[t]
    else:        
      if splitPower:
        return m.SOC[t] == m.SOC[t-1] + ( enableBattery * (m.powerBatteryNeg[t-1] + m.powerBatteryPos[t-1]) / intervalsPerHour )   
      else:
        return m.SOC[t] == m.SOC[t-1] + ( enableBattery * m.powerBattery[t-1] / intervalsPerHour ) 
m.State_of_charge = en.Constraint(m.T, rule = State)

#MG new power out (generate/export/discharge) terms
def power_export(m, t):
  return m.powerExport[t] ==  \
      ( m.powerBatteryNeg[t] * enableBattery * (1 - marginalCostBattery /  ( m.price[t] + 0.000001) ) ) \
      + m.fcastPV[t] * (1 - marginalCostPV /  ( m.price[t] + 0.000001) ) \
      + ( m.fcastPV[t] * m.booleanPV[t] * (1 - marginalCostPV /  ( m.price[t] + 0.000001) ) ) \
      + ( m.powerGenset[t] * ( 1 - gensetHeatRate * costGas / ( m.price[t] + 0.000001) ) * (1 - marginalCostGenset /  ( m.price[t] + 0.000001) ) ) 
      #+ ( deltaPVSRNeg[t]  * enableDCM )  #+ m.powerGenset[t]
m.powerExportConst = en.Constraint(m.T, rule = power_export)

#MG new power in (consume/import/charge) terms
#This follows sign constraint, -ve means export
def power_import(m, t):
  return m.powerImport[t] == \
      ( m.powerBatteryPos[t]  * enableBattery * (1 - marginalCostBattery /  ( m.price[t] + 0.000001) ) ) \
      + m.loadSR[t]  \
      + m.powerLoadBank[t]
      #+ ( deltaPVSRPos[t]  * enableDCM )
m.powerImportConst = en.Constraint(m.T, rule = power_import)


if enableNetInterconnectConstraint:
  def net_export_constraint(m, t):
    return -netInterconnectConstraint <= m.powerBatteryNeg[t] + m.powerBatteryPos[t] + ( m.fcastPV[t] * m.booleanPV[t] ) + m.powerGenset[t] + m.powerLoadBank[t] + m.loadSR[t] <= netInterconnectConstraint
  m.netInterconnectConstraint = en.Constraint(m.T, rule = net_export_constraint)

#=============Solve the model==========================
from pyomo.opt import SolverFactory
opt = SolverFactory('glpk')

print('duration of initialization prior to solve: ' + str(np.round( timer() - start , 2) ) + ' seconds' )
start = timer()
print('solving...')
results = opt.solve(m)
print('duration of solve : ' + str(np.round( timer() - start , 2) ) + ' seconds' )

#m.display() #Uncomment to display results
#=============/Solve the model==========================


#=============Retrieve results==============================
SOCSolved = np.zeros( (len(price)) )
powerBatterySolved = np.zeros( (len(price)) )
powerBatteryNegSolved = np.zeros( (len(price)) )
powerBatteryPosSolved = np.zeros( (len(price)) )
powerLoadBankSolved = np.zeros( (len(price)) )
loadSRSolved = np.zeros( (len(price)) )
powerGensetSolved = np.zeros( (len(price)) )
booleanPVSolved = np.zeros( (len(price)) )
priceSolved = np.zeros( (len(price)) )
netInterconnectPower = np.zeros( (len(price)) )
#negPriceOut = np.zeros( (len(price)) )
#posPriceOut = np.zeros( (len(price)) )

#Write model to log file and copy Python source code for reference
if createLogfile:
  with open(dirLogsOut + str(epochTime) + '_' + "log_file.txt", "w") as fout:
    m.pprint(ostream = fout)
  if not runOnVM:
    copyfile(currFilePath + '\\' + currFileName, dirLogsOut + str(epochTime) + '_'  + currFileName)

#Access variables
j = 0
for v in m.component_objects(en.Var, active=True):
    print("Variable",v)
    for index in v:
        #print ("   ",index, en.value(v[index]))
        if j == 0:
          powerBatterySolved[index] = en.value(v[index])      
        elif j == 1:
          SOCSolved[index] = en.value(v[index])
        elif j == 2:
          powerBatteryPosSolved[index] = en.value(v[index])
        elif j == 3:
          powerBatteryNegSolved[index] = en.value(v[index])
        elif j == 4:
          powerLoadBankSolved[index] = en.value(v[index])
        elif j == 5:
          booleanPVSolved[index] = en.value(v[index])
        elif j == 6:
          powerGensetSolved[index] = en.value(v[index])
    j+=1
        
#access parameters (to double check)
#Don't really need neg and pos since they are just the sign-separated price
j = 0
for parmobject in m.component_objects(en.Param, active=True):
    print ("Parameter "+str(parmobject.name))
    for index in parmobject:
        #print ("   ",index, en.value(parmobject[index]))
        if j == 0:
          priceSolved[index] = en.value(parmobject[index])
        elif j == 1:
          loadSRSolved[index] = en.value(parmobject[index])
#        elif j == 2:
#          posPriceOut[index] = en.value(parmobject[index])
    j+=1
      
SOCSolvedPercent = SOCSolved / SOCMax

scheduledPVSolved = fcastPV * booleanPVSolved

#Consistency check
if splitPower:
  a = powerBatteryPosSolved > 0  
  b = powerBatteryNegSolved > 0
  batteryError = np.sum(a*b)
  if batteryError:
    print('WARNING: YOU SEEM TO HAVE A TIME WHEN THE BATTERY WANTED TO CHARGE AND DISCHARGE SIMULTANEOUSLY!!!')
    print('Continuing on...')

#Compile power out from power out pos and power out neg
if splitPower:
  powerBatterySolved = ( powerBatteryPosSolved + powerBatteryNegSolved )

#Calculate revenue/cost
netCashBattery = -priceSolved * powerBatterySolved / intervalsPerHour / 1000 #div by 1000 bc price in MW
#Battery revenue + load bank revenue + solar revenue - SR load costs
netCashTotal = -( \
        ( priceSolved * powerBatterySolved / intervalsPerHour ) \
        + (priceSolved * powerLoadBankSolved / intervalsPerHour) \
        + (priceSolved * scheduledPVSolved / intervalsPerHour) \
        + (priceSolved * loadSRSolved / intervalsPerHour) \
        + (priceSolved * powerGensetSolved / intervalsPerHour) \
        ) / 1000  #div by 1000 because price in MWh, convert to KWh
print("Net Cash Flow is $: " + str(np.round(np.sum (netCashTotal) , 2) ) )  #I HAVE NEGATED - BETTER TO BE CONSISTENT WITH NEG FROM BEGINNING
cashFlowTotal = np.cumsum(netCashTotal)
#netCashBattery = np.cumsum(netCashBattery)

#generate cash flow if the assets didn't run
cashFlowSROnly = np.cumsum( -priceSolved * loadSRSolved / intervalsPerHour ) / 1000

print("Battery-only revenue is $: " + str(np.round(np.sum (netCashBattery) , 2) ) )  #I HAVE NEGATED - BETTER TO BE CONSISTENT WITH NEG FROM BEGINNING
cashflowBattery = np.cumsum(netCashBattery)

print('Average state of charge throughour period is: ' + str(np.round(100*np.average(SOCSolvedPercent))) + '%')

netInterconnectPower = powerBatterySolved + loadSRSolved + scheduledPVSolved + powerGensetSolved + powerLoadBankSolved

#=============/Retrieve results==============================

#=============Assemble output file==============================
planOut = pd.DataFrame(index = price.index)
planOut['battery_kW'] = powerBatterySolved
#planOut.loc[:,'battery_enable'] = 0
planOut.loc[ planOut['battery_kW'] != 0 , 'battery_enable']  = 'enable'
planOut.loc[ planOut['battery_kW'] == 0 , 'battery_enable']  = 'disable'
planOut['PV_kW'] = scheduledPVSolved
planOut.loc[ planOut['PV_kW'] != 0 , 'PV_enable']  = 'enable'
planOut.loc[ planOut['PV_kW'] == 0 , 'PV_enable']  = 'disable'
planOut['loadBank_kW'] = powerLoadBankSolved
planOut.loc[ planOut['loadBank_kW'] != 0 , 'loadBank_enable']  = 'enable'
planOut.loc[ planOut['loadBank_kW'] == 0 , 'loadBank_enable']  = 'disable'
planOut['genset_kW'] = powerGensetSolved
planOut.loc[ planOut['genset_kW'] != 0 , 'genset_enable']  = 'enable'
planOut.loc[ planOut['genset_kW'] == 0 , 'genset_enable']  = 'disable'

broken_barh_plot.plot_enables(planOut, dirLogsOut, epochTime)

#AUTOGRID NEEDS DISCHARGE +, SO FLIP SIGN HERE
planOut['battery_kW'] *= battery_sign

planOut = planOut.set_index(fcast.index)
planOut.to_pickle(dirPlanOut + str(epochTime) + '_' + 'planOut.pkl')
planOut.to_csv(dirPlanOut + str(epochTime) + '_' + 'planOut.csv')

#=============/Assemble output file==============================

#=============Plot results==============================
        
#plt.figure()
#plt.plot(priceSolved)
#plt.plot(powerBatterySolved)



fig = plt.figure(figsize = (12,12))
ax1 = fig.add_subplot(411)
ax1.plot(priceSolved, 'b-')
ax1.set_xlabel('time')
# Make the y-axis label, ticks and tick labels match the line color.
ax1.set_ylabel('price ($/MWh)', color='b')
ax1.tick_params('y', colors='b')

ax2 = fig.add_subplot(412)
ax2.plot(SOCSolvedPercent*100, 'r')
ax2.set_ylim(0 , 100)
ax2.set_ylabel('SOC (percent)', color='r')
ax2.tick_params('y', colors='r')

ax3 = fig.add_subplot(413)
ax3.plot(cashFlowTotal, 'g')
ax3.plot(cashFlowSROnly, 'k')
ax3.legend(['MG assets enabled', 'SR bldg only' ])
ax3.set_ylabel('cash flow ($)', color='g')
ax3.tick_params('y', colors='g')

ax4 = fig.add_subplot(414)
ax4.plot(powerBatterySolved, 'g')
ax4.plot(powerLoadBankSolved, 'r')
ax4.plot(scheduledPVSolved, 'y')
ax4.plot(fcastPV, 'r--', linewidth = 0.5)
ax4.plot(loadSRSolved, 'b')
#ax4.plot(scheduledPVSolved + loadSRSolved, linewidth = .75)
ax4.plot(powerGensetSolved, 'c')
ax4.plot(netInterconnectPower, 'k', linewidth = 2.5)
ax4.set_ylabel('Asset power (+ve import), (kW)', color='g')
ax4.tick_params('y', colors='g')
plt.legend([ 'Battery' , 'loadBank' , 'PV sched (scaled)', 'PV forecast' , 'loadSR', 'Genset', 'Net Interconnect'], loc = 4)
fig.tight_layout()

plt.savefig(dirLogsOut + str(epochTime) + '_plan_figure.png')
#plt.show()

if splitPower:
  plt.figure()
  plt.plot(powerBatteryPosSolved, 'r')
  plt.plot(powerBatteryNegSolved)
  plt.plot(powerBatteryPosSolved + powerBatteryNegSolved, 'g')

#=========Plot filled in color chart============
x = np.arange(len(loadSRSolved))

line1pos = loadSRSolved
line2pos = line1pos + powerLoadBankSolved
line3pos = line2pos + powerBatterySolved.clip(min=0)
line1neg = scheduledPVSolved
line2neg = line1neg + powerGensetSolved
line3neg = line2neg + powerBatterySolved.clip(max=0)
netInterconnect =  loadSRSolved + powerBatterySolved + powerLoadBankSolved + powerGensetSolved + scheduledPVSolved

fig = plt.figure(figsize = (12,5))
ax = plt.gca()
ax.fill_between(x, 0, line1pos, label = 'SR Load')
ax.fill_between(x, line1pos , line2pos, label = 'Load Bank')
ax.fill_between(x, 0, line1neg, label = 'PV')
ax.fill_between(x, line1neg, line2neg, label = 'Genset')
#where is technically not needed since split into +/- above.  Keep for posterity
ax.fill_between(x, line2pos , line3pos, where=powerBatterySolved >= 0, label = 'Battery Charge')
ax.fill_between(x, line2neg , line3neg, where=powerBatterySolved < 0, label = 'Battery Discharge')

ax.plot(line1pos, 'w' ,linewidth = 0.5)
ax.plot(line2pos, 'w',linewidth = 0.5)
ax.plot(line3pos, 'w',linewidth = 0.5)
ax.plot(line1neg, 'w' ,linewidth = 0.5)
ax.plot(line2neg, 'w',linewidth = 0.5)
ax.plot(line3neg, 'w',linewidth = 0.5)
ax.plot(netInterconnect, 'k', label = 'net Interconnect')
plt.legend()
plt.xlabel('time (interval)')
plt.ylabel('power (kW); +ve is import')
plt.title('Asset output power plan, stacked')
#plt.xlim([-10, 300])

#plt.ylim(-500, 350)

plt.savefig(dirLogsOut + str(epochTime) + '_plan_figure_stacked.png')



#=============/Plot results==============================