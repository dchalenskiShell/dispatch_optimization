# -*- coding: utf-8 -*-
"""
Created on Fri Mar  1 10:31:07 2019

@author: David.Chalenski
"""

import numpy as np
import matplotlib.pyplot as plt
import pandas as pd

#rng = pd.date_range('1/1/2018', periods = 365)

#df = pd.DataFrame()

savefigs = False
re_read_xlsx = False

dir = "C:/Users/David.Chalenski/OneDrive - Shell/Documents/ESIS/Microgrid/data/2018-2019 PV load data for demand management code/"
fname = "Daves SR-PV data 2.28.19.xlsx"

#want to re-read this input file?
if re_read_xlsx:
  #frame to hold rtm data
  df_in = pd.DataFrame()
  
  #real time market prices file
  #Excel file  below is edited and produces zero errors
  

  excel_in = pd.ExcelFile(dir + fname, index_col=0, parse_dates = True)
    
  print(excel_in.sheet_names)
  print(len(excel_in.sheet_names))
  
  #read in and combine all sheets from excel file into dataframe
  #for i in np.arange(len(excel_in.sheet_names)):
  #print('working on sheet ' + str(excel_in.sheet_names[i]))
  #sheet = pd.read_excel(excel_in, sheetname = '2Python')
  #print(sheet.shape)
  
    
  #read in and combine all sheets from excel file into dataframe
  for i in np.arange(len(excel_in.sheet_names)):
    print('working on sheet: ' + str(excel_in.sheet_names[i]))
    sheet = pd.read_excel(excel_in, sheetname = i)
    print(sheet.shape)
    
    df_in = df_in.append(sheet)
    
  print(list(df_in.columns))
  
  #df['Date'] = pd.to_datetime(df['Date'])
  #df = df.set_index(df['Date'])
  #df = df.drop(columns = 'Date')
  
  df_in.columns = ['PV_kw','SR_kw']
  
  #df = df.append(sheet)
  
  #df['Date'] = pd.to_datetime(df['Date'])
  #df = df.set_index(df['Date'])
  #df = df.drop(columns = 'Date')
  
  #df.columns = ['1hr','60hr','30hr','15hr','10hr','5hr','3hr','2hr']
  print(list(df_in.columns))
  
  #uncomment if you want to rewrite the pickle
  df_in.to_pickle(dir + 'df_SR_load_PV_in_raw.pkl')

else:
  df_in = pd.read_pickle(dir + 'df_SR_load_PV_in_raw.pkl')

print(df_in.describe())

df = df_in.sort_index()

#clip any negative values to 0
df.PV_kw.clip(lower=0, inplace=True)
df.SR_kw.clip(lower=0, inplace=True)

num_bins = 20
counts, bin_edges = np.histogram (df['PV_kw'].values, bins=num_bins, normed=True)
cdf = np.cumsum(counts)

plt.close('all')
plt.plot (bin_edges[1:], counts)
plt.figure()
plt.plot(bin_edges[1:], cdf/cdf[-1])

q = 50 #random percentile to sample, can check against describe above at 50%
print(np.percentile(df['PV_kw'], q))

interval_duration = 15 #minutes in meter interval
df_avg_15m = df.groupby(pd.Grouper(freq='15Min')).aggregate(np.average)

#Generate columns with energy generated/consumed per 15 minutes interval
df_avg_15m['SR_kwh'] = df_avg_15m.SR_kw /4 #4 15-min intervals per hour
df_avg_15m['PV_kwh'] = df_avg_15m.PV_kw / 4

"""
df = df_in.set_index(['type','month', 'node'])

#remove rows without week or weekend
df = df[df['daytype'] != 'peak']
df = df.drop(index = ['cooling','refrigeration','water-heating','naturalgas-only'], level = 0)
#df_week = df[df['daytype'] != 'week']

test1 = df_elec.index.weekday
test2 = df_elec.index.month_name()

test3 = pd.DataFrame()
test3 = df[df[]]
df_elec.groupby('M')

plt.close('all')

plt.figure()    
#Plot SOC after discharge events for all events
n_bins=20  
arr = plt.hist(df.loc[:,'1hr'], bins=n_bins)
height_shift = arr[0].max() / 20
for i in range(n_bins):
    #add y=500 so they're above the bars a bit
    plt.text(arr[1][i] , arr[0][i] + height_shift, str(arr[0][i]), rotation=20)
plt.xlabel('asdf')
plt.ylabel('asd')
plt.title('asdf') 
if savefigs:
    plt.savefig('.png')

plt.figure()
arr = plt.hist(df[df['1hr'] > 100],bins=n_bins)
height_shift = arr[0].max() / 20
for i in range(n_bins):
    #add y=500 so they're above the bars a bit
    plt.text(arr[1][i] , arr[0][i] + height_shift, str(arr[0][i]), rotation=20)
plt.xlabel('asdf')
plt.ylabel('asd')
plt.title('asdf') 
if savefigs:
    plt.savefig('.png')
"""