# -*- coding: utf-8 -*-
"""
Created on Sun Nov 18 15:40:52 2018

@author: David.Chalenski

https://tdhopper.com/blog/my-python-environment-workflow-with-conda/

https://stackoverflow.com/questions/34119866/setting-up-and-using-meld-as-your-git-difftool-and-mergetool

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
  A source/sink check so that all possible paths for energy/to from an asset are included - this is more of the GUI implementation
  
  TO IMPLEMENT SHORTER TERM
  Comment code
  Battery from PV, generator, grid
  SR from any asset (generator, PV, battery, grid)
  Cash flow and actual cost curve (e.g. with marginal costs)
  Plat the future times as distributions (e.g. look at 5:00-5:05, see how much it varies as
     you get new information throughout the day)
  Energy export/import constraint (to meet an obligation)
  Check close to 0 for battery net - do the marginal costs and degradation costs screw it up???
  Input Fcast PV had some negative values - for now I clip all input values below 0
  Ensure PV can curtail - may have been broekn after removed booleanPV control due ot battery charge from PV
  Add a check block to see if RT price - marginal prices goes negative - will expose weird fringe cases
  
  2018-01-02 Created v3_testing
    Plan to change structure of code, going from constraints of import/export to moving terms into the objective function
    Updating/changing variable names
    removed PV curtail and let be solved endogenously
    
  2019-02-12
    Implemented polarity priority convention - highest priority assets according to list below have sources/sinks
      relative to themselves.  e.g. battery will always have charge/discharge to any other location relative to its import/export 
      PV will source to SR
      SR will only consume from grid
      This was implemented because battery polarity is most confusion (both +/-), so we can orient to most complicated asset
      Polarity will always be tricky, as a positive PV profile will have to be split into multiple portiont goign in different directions
      with different polarities (PV charging battery will be seen as battery charge, so +, even though  generating would be -)
    0) forecasts (e.g. forecasts for any asset are from its perspective, so PV is a gen asset so it will be -, SR is a load so it will be +)
    1) gen/consume assets (batteries)
    2) Gen only assets (PV/genset)
    3) consume only assets (SR, load bank)
    4) Grid
    
  
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
from pyomo.opt import SolverFactory
#from pyomo.core import Var
#import pprint

plt.close('all')

#====================TESTING PARAMETERS================
#Some of these may need to be nuked when productized
#OLD#splitPower = True #Do you want to split power into pos and neg?
manipulateLoad = False #Artificially modify Sr load for testing purposes
manipulateLoadValue = 2 #can do, 2, 5, etc.

#====================/TESTING PARAMETERS================

#duration of calculation
start = timer()

createLogfile = True
currFilePath = os.path.dirname(os.path.realpath(__file__))
currFileName = os.path.basename(__file__)

#============Input variables===========
#NOTE: these are all positive kW values, irrespective of whether net demand or consume - negation is handled below in model definition
SOC_init = 500 #kWh  #WILL COME FROM TONY
SOC_fixed = 840
SOCMin = 200 #kWh
SOCMax = 1050 #kWh
powerBatteryMax = 250 #kW
powerPVMax = 350 #kW, not super important, as PV always constrained to below forecasted PV
PVScale = 5
SRScale = 1 #Remove (or set to 1) when productized
PVRoundTripEfficiency = 1
gensetHeatRate = 9.8
costGas = 3 #($/MWh)

#Marginal costs are currently used to prioritize these assets
#Higher marginal costs forces that asset to curtail over lower marginal cost assets
#This is currently not figured in to the actual revenue calculations
#They are arbitrary and small so as to have little impact if prices are low
marginalCostBattery = .0002 #Just priority, does not include degradation costs
#print("**********marginal cost of battery overwritten********")
marginalCostPV = .0001 #PV has the highest priority, lowest marginal cost
marginalCostGenset =  .0003 #This does not account for gas price, just priority
#CostToCharge = 1.5 #
#CostToDischarge = .5 #

enableBattery = True 
batteryDegrades = False #Do you want to figure in battery degradation?
enableBatteryToSR = False

enablePV = True 
enableBatteryFromGrid = True
enablePVtoBattery = True
enablePVtoSR = False
#enablePVCurtail = True #from TONY

enableGenset = False
enableGensetToSR = False
 
enableLoadBank = False 
enableSRLoad = True 



enableNCPReduction = False

returnToSOC = False #Need to implement
#enableDCM = False #enable demand charge management - Vestigial
clipNegPVInput = True #Make sure forecast is always - or 0 (sometimes it goes + by mistake)
#convertPriceInMWtoKW = False
enableMarginalCosts = True
resampleFcastsFiveMins = False
priceSpike = False
priceSpikeAmt = 50 #$/MWh for spike
#Sets all the parameters for the December PoC run
runOnVM = False
timeSoCFixed = 178

smoothSRLoad =  False  #BOMBS OUT - CREATES NANs FOR FIRST FEW INDICES, NEED TO BACK-TILE OR TRAINGLE FILTER
smoothingWindow = 5 #units of interval


#This is just a spoof to test demand charges on the SR building to ensure functionality of battery to SR
#Disable if already using NCP Reduction
DCMChargeSpoof = 5 * ~enableNCPReduction
RTPrice_boost = 0 #small modifier to RTMPrice to keep 0 price from blowing up. Delete when done testing

enableNetInterconnectConstraint = True 
netInterconnectConstraint = 300 #kW


#===========Demand Charge Parameters==================
#Optimization will use the greater of the two parameters below throughout each time step
#  to reduce the peak
#Value to initiate the demand charge reduction process [kWh consumed per interval]
#  If PV is running it can mitigate some demand charges.
#Pick a value which will not occur too frequently, typically informed by historical data
#Also must be a value the battery/BTM generation can reasonably reduce
#NCPSeedValueWithPV = 50 #NUKE #kWh
#NCPSeedValueWithoutPV = 70 #NUKE #kWh
#The value below is the demand charge NCP peak above which we want to shave, determined statistically from analysis
InterconnectNCPShaveValueInput = 140 # kWh #KEEP
#The rolling max peak actually observed. 
#Providing this code is not provided in this program - must be fed externally, to be developed
MonthlyObservedNCPeak = 45  #kWh #Probably keep this
RatchetPreviousTwelveMonthsObservedPeak = 45 #kWh
ratchetPercentage = 0.80

DEMANDCHARGECOST = .1
NCPRatchetTariffRate = 2 #$
NumberMonthsRatchet = 12

#Read parameters and forecasts files
if runOnVM:
  fdirFcast = 'E:/Optimization/inputs/'
  fname = 'inputs.pkl'
else:
  #fdirFcast = 'C:/Users/David.Chalenski/OneDrive - Shell/Documents/ESIS/Microgrid/dispatch optimization/python/dispatch_optimizer_v2/input/'
  fdirFcast = currFilePath + '\\input\\'
  #fname = 'forecast_all_topython_pkl.pkl'  #I used this for a lot of testing
  fname = 'input_DO_1day_sample.pkl'
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

#=============/Input Variables=============
battery_sign = 1 #AG reads positive as DISCHARGE, so need to flip sign if generating plan for them

dirLogsOut = currFilePath + '\\logs\\' #will come from TONY - log files
dirPlanOut = currFilePath + '\\logs\\'

epochTime = int(np.round(time.time(),0)) #will come from Tony

if not enableMarginalCosts:
  marginalCostBattery = marginalCostPV = marginalCostGenset = 0


#determine number of intervals per hour from input forecast
#e.g. 15-minute intervals = 4 per hour
intervalsPerHour = 60 / int(pd.infer_freq(fcast.index)[:-1]) 

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


#Setup test forecast cases
if False:
  #Test prices at 0 except 2-hour period in middle of day
  price.iloc[:] = 0
  price.iloc[110:150] = 150
  price.iloc[ 151:250 ] = 75
elif False:
  #Linearly increasing price
  price.iloc[:] = np.arange( len(fcast ) )
elif False:
  #Response to negative prices
  price.iloc[:] = 10
  price.iloc[ 51:75 ] = 50
  price.iloc[ 150:200 ] = 300
elif False:
  #Respond to positive and negative prices
  price.iloc[:] = 20
  #price.iloc[ 21:36 ] = -50 
  price.iloc[ 51:150 ] = 50
elif False:
  #Respond to positive and negative prices
  price.iloc[:] = 10
  #price.iloc[ 21:36 ] = 50 
  price.iloc[ 120:180 ] = 50
  price.iloc[ 180:210 ] = 75
  price.iloc[ 210: ] = 50
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
#assumes a fixed reduction and future value of value
#numbers taken from DH bids, XX% capacity remaining after YY years with 1 cycle per day
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
loadSR = ( fcast['fc_load_SR'].copy() * SRScale )
if manipulateLoad:
  loadSR.iloc[25:65] *= manipulateLoadValue
if not enableSRLoad:
  loadSR.iloc[:] = 0
loadSR.index = np.arange( len(fcast) )
if smoothSRLoad:
  loadSR = loadSR.rolling(smoothingWindow).mean()
loadSRDict = loadSR.to_dict()
#Read in forecast of solar PV in KW
#Note: PV is export, so power is negative
if clipNegPVInput:
  fcastPV = fcast['fc_solar_kw'].clip(lower=0).copy() *-1 * PVScale
else:
  fcastPV = fcast['fc_solar_kw'].copy() *-1 * PVScale
if not enablePV:
  fcastPV[:] = 0
fcastPV.index = np.arange( len(fcast) )

fcastPV.head()

#Setup test forecast cases
if False:
  #Test prices at 0 except 2-hour period in middle of day
  fcastPV[:] = 0
  fcastPV[110:150] = -1500
  fcastPV[ 150:250 ] = -375
elif False:
  #Linearly increasing price
  fcastPV[:] = np.arange( len(fcast ) )
elif False:
  fcastPV[:] = 0
  fcastPV[110:150] = -150
  fcastPV[ 151:250 ] = -75
elif False:
  fcastPV[:] = 0
  fcastPV[110:150] = -150
  fcastPV[ 151:250 ] = -75
    
fcastPV.head()
    
#Zero out PV where price forecasted to be negative
#if enablePVCurtail:
#  fcastPV = fcastPV * (price >= 0)
fcastPVDict = fcastPV.to_dict()


#================NCP reduction seed value and mask array=============
"""
if enablePV:
  NCPSeedValue = NCPSeedValueWithPV
else:
  NCPSeedValue = NCPSeedValueWithoutPV

#Create mask array which has values only for suspected peaks to reduce
#e.g. set to 0 if we don't want the optimization to reduce the peak because it has a low value
if enablePV:
  #FcastPV (-), loadSR (+), need a positive result when load remains after PV
  NCPMask = fcastPV + loadSR
else:
  NCPMask = loadSR

NCPMask[NCPMask < max(NCPSeedValue,MonthlyObservedNCPeak)] = 0
NCPMaskDict = NCPMask.to_dict()

if False:
  plt.figure()
  plt.plot(NCPMask)
  plt.plot(fcastPV)
  plt.plot(loadSR)
"""
#Shave peaks below either the statistically determined value or the actualy monthly observed peak
#this is probably where you will implement ratchet by incorporating an 80% from values seen from last year
#Also correct peak demand value if it is higher than our export constraint
InterconnectNCPShave = min(netInterconnectConstraint, max(InterconnectNCPShaveValueInput , MonthlyObservedNCPeak , ratchetPercentage*RatchetPreviousTwelveMonthsObservedPeak) )

netInterconnectConstraintExport = netInterconnectConstraint

print('Interconnect operating DCM shave limit is currently: ' + str(InterconnectNCPShave))
print('Interconnect net (physical) constraint is currently: ' + str(netInterconnectConstraint))

#============/Manipulate  inputs=======================

#Initialize Model
m = en.ConcreteModel()
  
#SETS
#RangeSet: start, end, step
#keep Python ordering by starting at 0
m.T = en.RangeSet(0, len(priceDict) - 1 )

#=========PARAMETERS===========
# # Real Time Price forecast, time t
# Don't use enable/disable on these, the forecasts should always be valid
m.price = en.Param(m.T, within = en.Reals, initialize = priceDict)
m.loadSR = en.Param(m.T, within = en.NonNegativeReals, initialize = loadSRDict)
m.fcastPV = en.Param(m.T, within = en.NonPositiveReals, initialize = fcastPVDict) #Must be 0 or zero, e.g. bounds = (none, 0)
m.NCPCharge = en.Param(m.T, within = en.NonNegativeReals, initialize = 0 ) # NCPMaskDict)
  
#==========VARIABLES=============
#Convention order in terms of polarity priority as defined above, 1) consume&gen ; 2) gen only ; 3) comsume only ; 4) grid
#First asset in variable name determines which has polarity priority: PVtoGrid is from PV's perspective, so a + number because gen
#All numbers are discharge power (note this is obviously instantaneous, not energy scaled for interval duration)
#Initialize most to 0 so final iteration remains finite
#OLD#m.powerBattery = en.Var( m.T, bounds=(-powerBatteryMax, powerBatteryMax), initialize = 0 )
m.SOC = en.Var(m.T, bounds=(SOCMin, SOCMax) ) 
m.batteryChargeFromGrid = en.Var( m.T, bounds=(0, powerBatteryMax * enableBattery * enableBatteryFromGrid), initialize = 0 ) 
m.batteryDischargeToGrid = en.Var( m.T, bounds=( -powerBatteryMax * enableBattery, 0 ), initialize = 0 ) 
m.batteryChargeFromPV = en.Var( m.T, bounds=(0, powerBatteryMax * enableBattery * enablePV * enablePVtoBattery), initialize = 0 ) 
m.batteryDischargeToSR = en.Var( m.T, bounds=(-powerBatteryMax * enableBattery * enableSRLoad * enableBatteryToSR, 0 ), initialize = 0 ) 
#m.batteryChargingBool = en.Var( m.T, within = en.Boolean , initialize = 0 ) #Does this need to be implemented somehow?* enableBattery
#m.batteryDischargingBool = en.Var( m.T, within = en.Boolean , initialize = 0 ) #* enableBattery
m.batteryChargingBool = en.Var( m.T, domain = en.Binary, initialize = 0 ) #Does this need to be implemented somehow?* enableBattery
m.batteryDischargingBool = en.Var( m.T, domain = en.Binary, initialize = 0 ) #* enableBattery
m.powerBatteryNetPos = en.Var( m.T, bounds=(0, powerBatteryMax), initialize = 0 ) #* enableBattery #Net Consume/charge
m.powerBatteryNetNeg = en.Var( m.T, bounds=(-powerBatteryMax, 0), initialize = 0 ) #* enableBattery#Generate/Discharge
m.powerLoadBank = en.Var( m.T, bounds=( 0 , powerLoadBankMax * enableLoadBank), initialize = 0 ) 
m.powerGenset = en.Var( m.T, bounds=( -powerGensetMax * enableGenset, 0 ), initialize = 0 ) 
#Will need a NET, then GenSet to SR, GenSet from Battery (which will go in battery section due to priority rules), Genset to Grid
m.PVtoGrid = en.Var( m.T, bounds=(-powerPVMax * enablePV, 0), initialize = 0 ) 
m.PVtoSR = en.Var( m.T, bounds=(-powerPVMax * enablePV * enableSRLoad * enablePVtoSR, 0), initialize = 0 ) 
#m.SRfromPV = en.Var(m.T, within = en.NonNegativeReals, initialize = 0)
m.SRfromGrid = en.Var(m.T, within = en.NonNegativeReals, initialize = 0)
#Demand charge adder, bounded at 0 or whatever value would bring us up to the max net interconnect constraint
m.demandChargeAdder = en.Var(m.T, bounds=(0, netInterconnectConstraint - InterconnectNCPShave), within = en.NonNegativeReals, initialize = 0)
#BELOW: NEED A VARIABLE TO ALLOW CHANGE OF STATE FOR DEMAND CHARGE SHAVE VALUE
m.netInterconnectConstraintImport = en.Var(m.T, bounds=(0 , netInterconnectConstraint), within = en.NonNegativeReals, initialize = InterconnectNCPShave)
"""WHY CAN'T THE ABOVE BE BOUNDED TO bounds = (0, netInterconnectConstraint),"""

#OBJECTIVE STATEMENT
"""things this does not do yet:
turn PV off 
return to SOC
"""
def Total_cost(model):
  #Note all powers + mean importing (buying/charging/consuming)
  #note: 0.000001 additions below were just to ensure not div/0 when testing price=0
  return sum(   
    (
    #SR building consume from grid
    ( m.SRfromGrid[t] * (1  + m.NCPCharge[t] / m.price[t]) )
    #===Battery Rules===
    #battery supply/discharge to grid
    # (-) * (1 - 0.01 / 25 ) * 25
    + ( m.batteryDischargeToGrid[t] * (1 - marginalCostBattery  /  ( m.price[t] + RTPrice_boost) ) ) 
    #Battery consume/charge from PV at grid price
    #(+) * (1 - 0.01 / 25 )
    + ( m.batteryChargeFromGrid[t] * (1 - marginalCostBattery +  m.NCPCharge[t] / (m.price[t] + RTPrice_boost) ) ) 
    #SR consume from Battery
    #
    + ( m.batteryDischargeToSR[t] * (  marginalCostBattery / ( m.price[t] + RTPrice_boost) ) ) 
    #Battery consume/charge from PV at ~0 marginal cost
    #(+) * (0.01 + 0.02) / 25
    + ( m.batteryChargeFromPV[t] * ( ( marginalCostBattery + marginalCostPV ) / ( m.price[t] + RTPrice_boost) ) ) 
    #PV supply to grid
    #(-) * (1- 0.01/25) * 25
    + ( m.PVtoGrid[t] * (1 - marginalCostPV / ( m.price[t] + RTPrice_boost ) ) )
    #SR consume from PV
    + ( m.PVtoSR[t] * ( marginalCostPV /  ( m.price[t] + RTPrice_boost) ) ) 
    #Genset supply to grid - ALGEBRA DOESN"T LOOK RIGHT HERE, CHECK LATER
    + ( m.powerGenset[t] * ( 1 - gensetHeatRate * costGas / ( m.price[t] + RTPrice_boost) ) * (1 - marginalCostGenset /  ( m.price[t] + RTPrice_boost) ) )
    #Load bank consume from grid
    + m.powerLoadBank[t]
    ) * m.price[t] 
    #Demand charge peak reduction
    + m.demandChargeAdder[t] * DEMANDCHARGECOST
    #NOT SURE IF BELOW WORK PROPERLY
    + ( m.powerBatteryNetPos[t] * degradationCostSlope * batteryDegrades) 
    - ( m.powerBatteryNetNeg[t] * degradationCostSlope * batteryDegrades)
    for t in m.T)
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
      return m.SOC[t] == m.SOC[t-1] + ( enableBattery * (m.powerBatteryNetNeg[t-1] + m.powerBatteryNetPos[t-1]) / intervalsPerHour )   
m.State_of_charge = en.Constraint(m.T, rule = State)

#Net battery pos (charge)
def battery_charge_net(m, t):
  return m.powerBatteryNetPos[t] == m.batteryChargeFromGrid[t] + m.batteryChargeFromPV[t]
m.batteryChargeNetConst = en.Constraint(m.T, rule = battery_charge_net )
#net battery neg (discharge)
def battery_discharge_net(m, t):
  return m.powerBatteryNetNeg[t] == m.batteryDischargeToGrid[t] + m.batteryDischargeToSR[t]
m.batteryDischargeNetConst = en.Constraint(m.T, rule = battery_discharge_net )

#battery charge can't exceed max power
def battery_charge_max(m, t):
  return m.powerBatteryNetPos[t] <= powerBatteryMax * m.batteryChargingBool[t]
m.batteryChargeMaxConst = en.Constraint(m.T, rule = battery_charge_max )

#battery discharge can't exceed max power
def battery_discharge_max(m, t):
  return m.powerBatteryNetNeg[t] >= -powerBatteryMax * m.batteryDischargingBool[t]
m.batteryDischargeMaxConst = en.Constraint(m.T, rule = battery_discharge_max )

#Battery can't charge and discharge in same period
def battery_charge_or_discharge(m, t):
  return m.batteryDischargingBool[t] + m.batteryChargingBool[t] <= 1 
m.batteryOnlyChargeorDischarge = en.Constraint(m.T, rule = battery_charge_or_discharge )

#Load of SR building must be met but source can be battery, grid or PV
def SR_consume_conservation(m, t):
  return m.loadSR[t] == -m.PVtoSR[t] + m.SRfromGrid[t] + m.batteryDischargeToSR[t]
m.SRConserveConst = en.Constraint(m.T, rule = SR_consume_conservation )
#Can't commit to using more PV than available from forecast
#The elements are different sign (battery charge and PV discharge), hence negative
def PV_commit_max(m, t):
  return m.fcastPV[t] <= m.PVtoSR[t] + m.PVtoGrid[t] - m.batteryChargeFromPV[t]
m.PVcommitConst = en.Constraint(m.T, rule = PV_commit_max )

#If demand charge adder goes up, ensure it stays up so we can continue to take advantage of
#(new) higher demand charge maximum
def demand_charge_adder_sustain(m, t):
  if t == 0:
    return  m.netInterconnectConstraintImport[t] == InterconnectNCPShave   #Initialize to the current observed (or statistically predicted) peak value 
  else:        
    return m.netInterconnectConstraintImport[t] == m.netInterconnectConstraintImport[t-1] + m.demandChargeAdder[t-1] 
m.demand_adder_sustain_const = en.Constraint(m.T, rule = demand_charge_adder_sustain)

if enableNetInterconnectConstraint:
  def net_export_constraint(m, t):
    return -netInterconnectConstraintExport <= (
      m.batteryDischargeToGrid[t] 
      #+ m.batteryChargeFromGrid[t] 
      + m.PVtoGrid[t]  
      + m.powerGenset[t] 
      + m.powerLoadBank[t] 
      #+ m.SRfromGrid[t]
      ) 
  m.netInterconnectConstraintExportConst = en.Constraint(m.T, rule = net_export_constraint)
  
  def net_import_constraint(m, t):
    return (
      #m.batteryDischargeToGrid[t] 
      m.batteryChargeFromGrid[t] 
      #+ m.PVtoGrid[t]  
      #+ m.powerGenset[t] 
      + m.powerLoadBank[t] 
      + m.SRfromGrid[t]
      ) <= m.netInterconnectConstraintImport[t] + m.demandChargeAdder[t]
  m.netInterconnectConstraintImportConst = en.Constraint(m.T, rule = net_import_constraint)

#=============Solve the model==========================

opt = SolverFactory('glpk')
#Time limit in seconds for GLPK
#opt.options['tmlim'] = 30

opt = SolverFactory('CPLEX')

#opt = SolverFactory('ipopt') #for MILP



print('duration of initialization prior to solve: ' + str(np.round( timer() - start , 2) ) + ' seconds' )
start = timer()
print('solving...')
results = opt.solve(m, tee = True)
print('duration of solve : ' + str(np.round( timer() - start , 2) ) + ' seconds' )

#m.display() #Uncomment to display results, but shoudl just check log file
#=============/Solve the model==========================


#=============Retrieve results==============================
#Write model to log file and copy Python source code for reference
if createLogfile:
  with open(dirLogsOut + str(epochTime) + '_' + "log_file.txt", "w") as fout:
    m.pprint(ostream = fout)
  if not runOnVM:
    copyfile(currFilePath + '\\' + currFileName, dirLogsOut + str(epochTime) + '_'  + currFileName)


SOCSolved = np.zeros( (len(price)) )
batteryChargeFromGridSolved = np.zeros( (len(price)) )
batteryDischargeToGridSolved= np.zeros( (len(price)) )
batteryChargeFromPVSolved = np.zeros( (len(price)) )
batteryDischargeToSRSolved = np.zeros( (len(price)) )
batteryChargingBoolSolved = np.zeros( (len(price)) )
batteryDischargingBoolSolved = np.zeros( (len(price)) )
powerBatteryNetPosSolved = np.zeros( (len(price)) )
powerBatteryNetNegSolved = np.zeros( (len(price)) )
powerLoadBankSolved = np.zeros( (len(price)) )
powerGensetSolved = np.zeros( (len(price)) )
PVtoGridSolved = np.zeros( (len(price)) )
PVtoSRSolved = np.zeros( (len(price)) )
SRfromGridSolved = np.zeros( (len(price)) )
loadSRSolved = np.zeros( (len(price)) )
DemandChargeAdderSolved = np.zeros( (len(price)) )
netInterconnectImportSolved = np.zeros( (len(price)) )
NCPChargeSolved = np.zeros( (len(price)) )

#powerBatterySolved 

booleanPVSolved = np.zeros( (len(price)) )

priceSolved = np.zeros( (len(price)) )
netInterconnectPower = np.zeros( (len(price)) )

SRfromBatterySolved = np.zeros( (len(price)) )
#negPriceOut = np.zeros( (len(price)) )
#posPriceOut = np.zeros( (len(price)) )

#Access variables
j = 0
for v in m.component_objects(en.Var, active=True):
    print("Variable #",str(j),v)
    for index in v:
        #print ("   ",index, en.value(v[index]))
        if j == 0:
          SOCSolved[index] = en.value(v[index])
        elif j == 1:
          batteryChargeFromGridSolved[index] = en.value(v[index])
        elif j == 2:
          batteryDischargeToGridSolved[index] = en.value(v[index])
          #powerBatteryNetNegSolved[index] 
        elif j == 3:
          batteryChargeFromPVSolved[index] = en.value(v[index])
        elif j == 4:
          batteryDischargeToSRSolved[index] = en.value(v[index])
        elif j == 5:
          batteryChargingBoolSolved[index] = en.value(v[index])
        elif j == 6:
          batteryDischargingBoolSolved[index] = en.value(v[index])
        elif j == 7:
          powerBatteryNetPosSolved[index] = en.value(v[index])
        elif j == 8:
          powerBatteryNetNegSolved[index] = en.value(v[index])
        elif j == 9:
          powerLoadBankSolved[index] = en.value(v[index])
        elif j == 10:
          powerGensetSolved[index] = en.value(v[index])
        elif j == 11:
          PVtoGridSolved[index] = en.value(v[index])
        elif j == 12:
          PVtoSRSolved[index] = en.value(v[index])
        elif j == 13:
          SRfromGridSolved[index] = en.value(v[index])
        elif j == 14:
          DemandChargeAdderSolved[index] = en.value(v[index])        
        elif j == 15:
          netInterconnectImportSolved[index] = en.value(v[index])
    j+=1
      
#access parameters (to double check)
#Don't really need neg and pos since they are just the sign-separated price
j = 0
for parmobject in m.component_objects(en.Param, active=True):
    print ("Parameter # ",str(j),str(parmobject.name))
    for index in parmobject:
        #print ("   ",index, en.value(parmobject[index]))
        if j == 0:
          priceSolved[index] = en.value(parmobject[index])
        elif j == 1:
          loadSRSolved[index] = en.value(parmobject[index])
        elif j == 3:
          NCPChargeSolved[index] = en.value(parmobject[index])
    j+=1
      
SOCSolvedPercent = SOCSolved / SOCMax

scheduledPVSolved = PVtoGridSolved + PVtoSRSolved - batteryChargeFromPVSolved

#Consistency check
a = powerBatteryNetPosSolved > 0  
b = powerBatteryNetNegSolved > 0
batteryError = np.sum(a*b)
if batteryError:
  print('WARNING: YOU SEEM TO HAVE A TIME WHEN THE BATTERY WANTED TO CHARGE AND DISCHARGE SIMULTANEOUSLY!!!')
  print('Continuing on...')

#Compile power out from power out pos and power out neg
powerBatterySolved = ( powerBatteryNetPosSolved + powerBatteryNetNegSolved )

#Calculate revenue/cost
netCashBattery = -priceSolved * ( batteryChargeFromGridSolved + powerBatteryNetNegSolved ) / intervalsPerHour / 1000 #div by 1000 bc price in MW
#Battery revenue + load bank revenue + solar revenue - SR load costs
netCashTotal = -( \
        ( priceSolved * ( batteryChargeFromGridSolved + powerBatteryNetNegSolved ) / intervalsPerHour ) \
        + (priceSolved * powerLoadBankSolved / intervalsPerHour) \
        + (priceSolved * PVtoGridSolved / intervalsPerHour) \
        + (priceSolved * SRfromGridSolved / intervalsPerHour) \
        + (priceSolved * powerGensetSolved / intervalsPerHour) \
        ) / 1000  #div by 1000 because price in MWh, convert to KWh
print("Net Cash Flow is $: " + str(np.round(np.sum (netCashTotal) , 2) ) )  #I HAVE NEGATED - BETTER TO BE CONSISTENT WITH NEG FROM BEGINNING
cashFlowTotal = np.cumsum(netCashTotal)
#netCashBattery = np.cumsum(netCashBattery)

#generate cash flow if the assets didn't run
cashFlowSROnly = np.cumsum( -priceSolved * SRfromGridSolved / intervalsPerHour ) / 1000

print("Battery-only revenue is $: " + str(np.round(np.sum (netCashBattery) , 2) ) )  #I HAVE NEGATED - BETTER TO BE CONSISTENT WITH NEG FROM BEGINNING
cashflowBattery = np.cumsum(netCashBattery)

print('Average state of charge throughout period is: ' + str(np.round(100*np.average(SOCSolvedPercent))) + '%')

netInterconnectPower = powerBatteryNetNegSolved + batteryChargeFromGridSolved +  PVtoGridSolved + loadSRSolved + powerGensetSolved + powerLoadBankSolved

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

#Broekn until pos neg battery charge fixed
#broken_barh_plot.plot_enables(planOut, dirLogsOut, epochTime)

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
ax4.axhline(y=InterconnectNCPShave ,linewidth=4, color='r')
plt.legend([ 'Battery' , 'loadBank' , 'PV sched (scaled)', 'PV forecast' , 'loadSR', 'Genset', 'Net Interconnect', 'NCP limit'], loc = 4)
fig.tight_layout()

plt.savefig(dirLogsOut + str(epochTime) + '_plan_figure.png')
#plt.show()

#Second subplotted figure
#fig, ax = plt.subplots(2,2, figsize = (12,12))
fig = plt.figure(figsize = (16,16))
ax1 = fig.add_subplot(321)
ax1.plot(powerBatteryNetPosSolved + 3, 'r')
ax1.plot(powerBatteryNetNegSolved + 5)
ax1.plot(powerBatteryNetPosSolved + powerBatteryNetNegSolved + 7, 'g')
plt.legend(['battery pos/charge', 'battery neg/discharge', 'battery net'])

ax2 = fig.add_subplot(322)
#plt.plot(powerBatterySolved, 'k', linewidth = 3)
ax2.plot(powerBatteryNetPosSolved + 5, linewidth = 3)
#plt.plot(powerBatteryNetNegSolved - 5, linewidth = 3)
ax2.plot(batteryChargeFromPVSolved - 3)
ax2.plot(batteryChargeFromGridSolved)
ax2.set_title('Battery power sources and sinks')
plt.legend([ 'Battery pos', 'battery from PV', 'battery from grid' ])


ax3 = fig.add_subplot(323)
ax3.plot(PVtoGridSolved)
ax3.plot(batteryChargeFromPVSolved+2, linewidth=3)
ax3.plot(fcastPV+5)
plt.legend(['Pv to grid', 'battery charge from PV +2', 'forecast PV +5'])

ax4 = fig.add_subplot(324)
ax4.plot(batteryChargeFromGridSolved)
ax4.plot(powerBatteryNetNegSolved)
ax4.plot(PVtoGridSolved)
ax4.plot(loadSRSolved)
ax4.plot(powerGensetSolved)
ax4.plot(powerLoadBankSolved)
ax4.plot(netInterconnectPower,'k', linewidth = 2.5)
ax4.axhline(y=InterconnectNCPShave ,linewidth=4, color='r')
plt.legend(['battery from grid','battery to grid', 'pv to grid','SR bldg','genset','load bank','net interconnect', 'NCP limit'])
ax4.set_title('contributions to net interconnect')

ax5 = fig.add_subplot(325)
ax5.plot(loadSRSolved, linewidth=3)
ax5.plot(SRfromGridSolved+2)
ax5.plot(batteryDischargeToSRSolved+3)
ax5.plot(PVtoSRSolved+4)
plt.legend(['load SR', 'SR from Grid +2', 'SR from battery +3', 'SR from PV +4'])

ax6 = fig.add_subplot(326)
ax6.plot(netInterconnectImportSolved)
ax6.plot(netInterconnectImportSolved + NCPChargeSolved - 3, '.')
ax6.plot(DemandChargeAdderSolved)
plt.legend(['Net Interconnect Import Limit','NCP Charge (-3)','Demand charge adder'])

plt.savefig(dirLogsOut + str(epochTime) + '_plan_figure2.png')

"""
ax6 = fig.add_subplot(326)
ax6.plot(batteryChargingBoolSolved)
ax6.plot(batteryDischargingBoolSolved)
plt.legend(['charging boolean', 'discharging boolean'])
"""



"""
Uncomment once want to use again
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
"""

"""
OLD - COMBINED INTO A SINGLE FIGURE ABOVE
#Check battery powers
plt.figure()
plt.plot(powerBatteryNetPosSolved, 'r')
plt.plot(powerBatteryNetNegSolved)
plt.plot(powerBatteryNetPosSolved + powerBatteryNetNegSolved, 'g')
plt.legend(['battery pos/charge', 'battery neg/discharge', 'battery net'])


plt.figure()
#plt.plot(powerBatterySolved, 'k', linewidth = 3)
plt.plot(powerBatteryNetPosSolved + 5, linewidth = 3)
#plt.plot(powerBatteryNetNegSolved - 5, linewidth = 3)
plt.plot(batteryChargeFromPVSolved - 3)
plt.plot(batteryChargeFromGridSolved)
plt.title('Battery power sources and sinks')
plt.legend([ 'Battery pos', 'battery from PV', 'battery from grid' ])

#Plot where the PV is going - battery or grid
plt.figure()
plt.plot(PVtoGridSolved)
plt.plot(batteryChargeFromPVSolved+2, linewidth=3)
plt.plot(fcastPV+5)
plt.legend(['Pv to grid', 'battery charge from PV +2', 'forecast PV +5'])

#look at all contributions to net interconnect constraint
plt.figure()
#netInterconnectPower = batteryChargeFromGridSolved +  PVtoGridSolved + loadSRSolved + powerGensetSolved + powerLoadBankSolved
#-netInterconnectConstraint <= m.powerBatteryNeg[t] + m.batteryChargeFromGrid[t] + m.PVtoGrid[t]  + m.powerGenset[t] + m.powerLoadBank[t] + m.loadSR[t] <= netInterconnectConstraint
plt.plot(batteryChargeFromGridSolved)
plt.plot(powerBatteryNetNegSolved)
plt.plot(PVtoGridSolved)
plt.plot(loadSRSolved)
plt.plot(powerGensetSolved)
plt.plot(powerLoadBankSolved)
plt.plot(netInterconnectPower,'k', linewidth = 2.5)
plt.legend(['battery from grid','battery to grid', 'pv to grid','SR bldg','genset','load bank','net interconnect'])
plt.title('contributions to net interconnect')

"""
#=============/Plot results==============================