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



q = 50 #random percentile to sample, can check against describe above at 50%
print(np.percentile(df['PV_kw'], q))

interval_duration = 15 #minutes in meter interval
df_avg_15m = df.groupby(pd.Grouper(freq='15Min')).aggregate(np.average)

#Generate columns with energy generated/consumed per 15 minutes interval
df_avg_15m['SR_kwh'] = df_avg_15m.SR_kw /4 #4 15-min intervals per hour
df_avg_15m['PV_kwh'] = df_avg_15m.PV_kw / 4
df_avg_15m['PV-SR_kwh'] = (df_avg_15m.PV_kw - df_avg_15m.SR_kw) / 4

num_bins = 20

#=========================PLOT ALL-YEAR DATA===========================
#=======PV plots=========
counts, bin_edges = np.histogram (df_avg_15m['PV_kwh'].values, bins=num_bins)
cdf = np.cumsum(counts)

plt.close('all')
fig1 = plt.figure(figsize = (12,12))


ax1 = fig1.add_subplot(321)
ax1.plot (bin_edges[1:], counts)
ax1.set_xlabel('Hist: PV energy generated per 15 minute interval')

ax2 = fig1.add_subplot(322)
ax2.plot(bin_edges[1:], cdf/cdf[-1])
ax2.set_xlabel('PV Energy gnerated per 15 min CDF')

#========SR=========
counts, bin_edges = np.histogram (df_avg_15m['SR_kwh'].values, bins=num_bins)
cdf = np.cumsum(counts)

ax3 = fig1.add_subplot(323)
ax3.plot (bin_edges[1:], counts)
ax3.set_xlabel('Hist: SR energy consumed per 15 minute interval')

ax4 = fig1.add_subplot(324)
ax4.plot(bin_edges[1:], cdf/cdf[-1])
ax4.set_xlabel('SR Energy consumed per 15 min CDF')

#============PV-SR===========
counts, bin_edges = np.histogram (df_avg_15m['PV-SR_kwh'].values, bins=num_bins)
cdf = np.cumsum(counts)

ax5 = fig1.add_subplot(325)
ax5.plot (bin_edges[1:], counts)
ax5.set_xlabel('Hist: PV-SR energy per 15 minute interval')

ax6 = fig1.add_subplot(326)
ax6.plot(bin_edges[1:], cdf/cdf[-1])
ax6.set_xlabel('PV-SR energy per 15 min interval CDF')

fig1.suptitle('Statistics for all 15-min data throughout year, all hours')



#=====================EXCLUDE N0N-PEAK/NIGHTTIME DATA=======================
df_avg_15m_day = df_avg_15m.between_time('06:00','18:00')
#=======PV plots=========
counts, bin_edges = np.histogram (df_avg_15m_day['PV_kwh'].values, bins=num_bins)
cdf = np.cumsum(counts)

fig2 = plt.figure(figsize = (12,12))


ax1 = fig2.add_subplot(321)
ax1.plot (bin_edges[1:], counts)
ax1.set_xlabel('Hist: PV energy generated per 15 minute interval')

ax2 = fig2.add_subplot(322)
ax2.plot(bin_edges[1:], cdf/cdf[-1])
ax2.set_xlabel('PV Energy gnerated per 15 min CDF')

#========SR=========
counts, bin_edges = np.histogram (df_avg_15m_day['SR_kwh'].values, bins=num_bins)
cdf = np.cumsum(counts)

ax3 = fig2.add_subplot(323)
ax3.plot (bin_edges[1:], counts)
ax3.set_xlabel('Hist: SR energy consumed per 15 minute interval')

ax4 = fig2.add_subplot(324)
ax4.plot(bin_edges[1:], cdf/cdf[-1])
ax4.set_xlabel('SR Energy consumed per 15 min CDF')

#============PV-SR===========
counts, bin_edges = np.histogram (df_avg_15m_day['PV-SR_kwh'].values, bins=num_bins)
cdf = np.cumsum(counts)

ax5 = fig2.add_subplot(325)
ax5.plot (bin_edges[1:], counts)
ax5.set_xlabel('Hist: PV-SR energy per 15 minute interval')

ax6 = fig2.add_subplot(326)
ax6.plot(bin_edges[1:], cdf/cdf[-1])
ax6.set_xlabel('PV-SR energy per 15 min interval CDF')

fig2.suptitle('Statistics for all 15-min data throughout year, daytime only')


#=========================Look at DAY VS NIGHT OF JUST PV-SR FOR QC===============
counts1, bin_edges1 = np.histogram (df_avg_15m['PV-SR_kwh'].values, bins=num_bins)
cdf1 = np.cumsum(counts1)
counts2, bin_edges2 = np.histogram (df_avg_15m_day['PV-SR_kwh'].values, bins=num_bins)
cdf2 = np.cumsum(counts2)

fig3 = plt.figure(figsize = (12,8))
ax1 = fig3.add_subplot(121)
ax1.plot (bin_edges1[1:], counts1)
ax1.plot (bin_edges2[1:], counts2)
ax1.legend(['all hours', '06:00-18:00 only'], loc='upper right')
ax1.set_xlabel('PV-SR energy [kWh] per 15 min interval')

ax2 = fig3.add_subplot(122)
ax2.plot(bin_edges1[1:], cdf1/cdf1[-1])
ax2.plot(bin_edges2[1:], cdf2/cdf2[-1])
ax2.legend(['all hours', '06:00-18:00 only'])
ax2.set_xlabel('PV-SR energy [kWh] per 15 min interval CDF')

fig3.suptitle('PV-SR all hours and day-only for QC')


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