# -*- coding: utf-8 -*-
"""
Created on Wed Dec 19 13:29:22 2018

@author: David.Chalenski
"""

# -*- coding: utf-8 -*-
"""
Created on Mon Dec 10 20:40:36 2018

@author: David.Chalenski

https://matplotlib.org/gallery/lines_bars_and_markers/broken_barh.html
"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import itertools
from toolz import interleave

#test = powerBatterySolved

#TO try: generate lsits of all consecutive 0s, then 1s.  Pull tuple of first
#and first+len of each list.  Check if first on or off, set color (blue/white) by
#this check

def plot_enables(planOut, dirOut, epochTime):

  colorBattery = []

  #BATTERY DISCHARGE
  #group all instances of consecutive occurrences of FIRST value (enable/disable)
  tmp_discharge = [ list(x[1]) for x in itertools.groupby(planOut.battery_kW.values.tolist(), lambda x: x >= 0 ) if not x[0] ]
  #battery not discharging, e.g. 0 or > 0
  tmp_charge = [ list(x[1]) for x in itertools.groupby(planOut.battery_kW.values.tolist(), lambda x: x < 0) if not x[0] ]
  
  #Iterate over longer of two arrays, e.g. we may start and end with disable
  if(len(tmp_discharge) <= len(tmp_charge)):
    length = len(tmp_discharge)
  else:
    length = len(tmp_charge)
  #broken_barh needs start and length of bar in tuple
  barsBatteryDischarge = []
  barsBatteryCharge = []
  counter = 0
  if planOut.battery_kW[0] < 0: # 'enable': 
    for i in np.arange(length):
      barsBatteryDischarge.append((counter, len(tmp_discharge[i]) - 1))
      #print(counter)
  #    if planOut.battery_kW[counter] < 0:
  #      #we are discharging
  #      colorBattery.append('green')
  #    else:
  #      colorBattery.append('red')
      counter += len(tmp_discharge[i]) + len(tmp_charge[i])
      #bars.append((counter, counter + len(tmp_arr_disable[i]) - 1))
      #counter += len(tmp_arr_disable[i])
  else:
    #counter += len(tmp_charge[0])
    for i in np.arange(length):
      barsBatteryDischarge.append((counter + len(tmp_charge[i]), len(tmp_discharge[i] )))
      counter += len(tmp_discharge[i])   + len(tmp_charge[i]) #Need to figure this out, if doesn't end on disable
  
  #BATTERY CHARGE
  #group all instances of consecutive occurrences of FIRST value (enable/disable)
  #battery charge, e.g. kW < 0
  tmp_charge = [ list(x[1]) for x in itertools.groupby(planOut.battery_kW.values.tolist(), lambda x: x <= 0) if not x[0] ]
  tmp_discharge = [ list(x[1]) for x in itertools.groupby(planOut.battery_kW.values.tolist(), lambda x: x > 0) if not x[0] ]

  #Iterate over longer of two arrays, e.g. we may start and end with disable
  if(len(tmp_charge) <= len(tmp_discharge)):
    length = len(tmp_charge)
  else:
    length = len(tmp_discharge)
  #broken_barh needs start and length of bar in tuple
  colorBattery = []
  counter = 0
  if planOut.battery_kW[0] > 0:# 'enable':
    for i in np.arange(length):
      barsBatteryCharge.append((counter, len(tmp_charge[i]) - 1))
      print(counter)
      counter += len(tmp_charge[i]) + len(tmp_discharge[i])
      #bars.append((counter, counter + len(tmp_arr_disable[i]) - 1))
      #counter += len(tmp_arr_disable[i])
  else:
    #counter += len(tmp_discharge[0])
    for i in np.arange(length):
      barsBatteryCharge.append((counter + len(tmp_discharge[i]), len(tmp_charge[i] )))
      counter += len(tmp_charge[i])   + len(tmp_discharge[i]) #Need to figure this out, if doesn't end on disable

  #===PV===
  #group all instances of consecutive occurrences of FIRST value (enable/disable)
  tmp_enable = [ list(x[1]) for x in itertools.groupby(planOut.PV_enable.values.tolist(), lambda x: x == 'disable') if not x[0] ]
  tmp_disable = [ list(x[1]) for x in itertools.groupby(planOut.PV_enable.values.tolist(), lambda x: x == 'enable') if not x[0] ]
  #Iterate over longer of two arrays, e.g. we may start and end with disable
  if(len(tmp_enable) <= len(tmp_disable)):
    length = len(tmp_enable)
  else:
    length = len(tmp_disable)
  #broken_barh needs start and length of bar in tuple
  barsPV = []
  counter = 0
  if planOut.PV_enable[0] == 'enable': 
    for i in np.arange(length):
      barsPV.append((counter, len(tmp_enable[i]) - 1))
      counter += len(tmp_enable[i]) + len(tmp_disable[i])
      #bars.append((counter, counter + len(tmp_arr_disable[i]) - 1))
      #counter += len(tmp_arr_disable[i])
  else:
    #counter += len(tmp_disable[0])
    for i in np.arange(length):
      barsPV.append((counter + len(tmp_disable[i]), len(tmp_enable[i] )))
      counter += len(tmp_enable[i])   + len(tmp_disable[i]) #Need to figure this out, if doesn't end on disable
  
  
  #==Load Bank==
  #Generate lists of all consecutive positive instantaneous power events e.g. charging
  #group all instances of consecutive occurrences of FIRST value (enable/disable)
  tmp_enable = [ list(x[1]) for x in itertools.groupby(planOut.loadBank_enable.values.tolist(), lambda x: x == 'disable') if not x[0] ]
  tmp_disable = [ list(x[1]) for x in itertools.groupby(planOut.loadBank_enable.values.tolist(), lambda x: x == 'enable') if not x[0] ]
  #Iterate over longer of two arrays, e.g. we may start and end with disable
  if(len(tmp_enable) <= len(tmp_disable)):
    length = len(tmp_enable)
  else:
    lengh = len(tmp_disable)
  #broken_barh needs start and length of bar in tuple
  barsLoadBank = []
  counter = 0
  if planOut.loadBank_enable[0] == 'enable': 
    for i in np.arange(length):
      barsLoadBank.append((counter, len(tmp_enable[i]) - 1))
      counter += len(tmp_enable[i]) + len(tmp_disable[i])
      #bars.append((counter, counter + len(tmp_arr_disable[i]) - 1))
      #counter += len(tmp_arr_disable[i])
  else:
    #counter += len(tmp_disable[0])
    for i in np.arange(length):
      barsLoadBank.append((counter + len(tmp_disable[i]), len(tmp_enable[i] )))
      counter += len(tmp_enable[i])   + len(tmp_disable[i]) #Need to figure this out, if doesn't end on disable
  
  
  #==Genset==
  #Generate lists of all consecutive positive instantaneous power events e.g. charging
  #group all instances of consecutive occurrences of FIRST value (enable/disable)
  tmp_enable = [ list(x[1]) for x in itertools.groupby(planOut.genset_enable.values.tolist(), lambda x: x == 'disable') if not x[0] ]
  tmp_disable = [ list(x[1]) for x in itertools.groupby(planOut.genset_enable.values.tolist(), lambda x: x == 'enable') if not x[0] ]
  #Iterate over longer of two arrays, e.g. we may start and end with disable
  if(len(tmp_enable) <= len(tmp_disable)):
    length = len(tmp_enable)
  else:
    length = len(tmp_disable)
  #broken_barh needs start and length of bar in tuple
  barsGenset = []
  counter = 0
  if planOut.genset_enable[0] == 'enable': 
    for i in np.arange(length):
      barsGenset.append((counter, len(tmp_enable[i]) - 1))
      counter += len(tmp_enable[i]) + len(tmp_disable[i])
      #bars.append((counter, counter + len(tmp_arr_disable[i]) - 1))
      #counter += len(tmp_arr_disable[i])
  else:
    #counter += len(tmp_disable[0])
    for i in np.arange(length):
      barsGenset.append((counter + len(tmp_disable[i]), len(tmp_enable[i] )))
      counter += len(tmp_enable[i])   + len(tmp_disable[i]) #Need to figure this out, if doesn't end on disable
  
  
  #plt.close('all')
  #Colors: https://coolors.co/cee7e6-96e2c6-457f6b-243e36-293132
  #https://towardsdatascience.com/customizing-plots-with-python-matplotlib-bcf02691931f
  #https://color.adobe.com/create/color-wheel/
  #https://matplotlib.org/users/colormaps.html
  #Colors taken from fill between module
  fig, ax = plt.subplots(figsize = (12,5), edgecolor = 'r')# '#243e36')
  ax.broken_barh(barsGenset, (42, 6), facecolors='#d62728')
  ax.broken_barh(barsLoadBank, (32, 6), facecolors='#ff7f0e')
  ax.broken_barh(barsPV, (22, 6), facecolors='#2ca02c')               
  ax.broken_barh(barsBatteryCharge, (12, 6), facecolors='#9467bd')               
  ax.broken_barh(barsBatteryDischarge, (12, 6), facecolors='#8c564b')               
  #ax.broken_barh([(10, 50), (100, 20), (130, 10)], (20, 9),
  #               facecolors=('red', 'yellow', 'green'))
  ax.set_ylim(5, 55)
  #ax.set_xlim(0, len(planOut))
  ax.set_xlabel('Time (interval number)')
  ax.set_yticks([15, 25, 35, 45])
  ax.set_yticklabels(['Battery', 'PV', 'Load Bank', 'Genset'])
  plt.legend([ 'Genset on', 'Load Bank on','PV on','Battery Charge', 'Battery Discharge'] )
  ax.spines['top'].set_visible(False)
  ax.spines['right'].set_visible(False)
  #ax.grid(True)
  #ax.annotate('race interrupted', (61, 25),
  #            xytext=(0.8, 0.9), textcoords='axes fraction',
  #            arrowprops=dict(facecolor='black', shrink=0.05),
  #            fontsize=16,
  #            horizontalalignment='right', verticalalignment='top')
  
  plt.show()
  
  plt.savefig(dirOut + str(epochTime) + '_plan_figure_assets_enable.png')
  
  return


##generate list of all consecutive idle events e.g. could potentially charge
#tmp_idle = [ list(x[1]) for x in itertools.groupby(df.power_inst_mw.values.tolist(), lambda x: x != 0) if not x[0] ]
##convert to numpy arrays

#non_discharge_events = np.array([np.array(xi) for xi in tmp_idle])
