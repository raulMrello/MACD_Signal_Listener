#!/usr/bin/env python
# -*- coding: utf-8 -*-

####################################################################################
# Librerías de manejo de datos 
import pandas as pd
import numpy as np

####################################################################################
# Librerías de visualización
import plotly
import plotly.plotly as py
import plotly.graph_objs as go
from plotly.graph_objs import *
from plotly.tools import FigureFactory as FF
import plotly.tools as tls

####################################################################################
# TA-Lib: instalación y carga de la librería
import talib

####################################################################################
# Otras utilidades
import datetime
import time
import os
import sys
import math
import pickle
from enum import Enum
import logging


####################################################################################
####################################################################################
####################################################################################


class ZIGZAG_Events():
  def __init__(self):
    self.clear()

  def clear(self):
    self.ZIGZAG_StartMinSearch = False
    self.ZIGZAG_StartMaxSearch = False

  def any(self):
    if self.ZIGZAG_StartMinSearch or self.ZIGZAG_StartMaxSearch:
      return True
    return False

  def info(self):
    result =''
    if self.ZIGZAG_StartMinSearch:
      result += 'ZigZagStartMinSearch '
    if self.ZIGZAG_StartMaxSearch:
      result += 'ZigZagStartMaxSearch '
    return result


####################################################################################
####################################################################################
####################################################################################

class ZIGZAG_Signal_Listener():
  def __init__(self, level=logging.WARN):    
    self.__logger = logging.getLogger(__name__)
    self.__logger.setLevel(level)
    self.__df = None
    self.__events = ZIGZAG_Events()
    self.__logger.info('Created!')

  def ZIGZAG(self, df, minbars=12, bb_period=20, bb_dev = 2.0, bb_sma=[50], nan_value = 0.0, level=logging.WARN):    
    """Builds a ZIGZAG indicator based on Bollinger Bands overbought and oversell signals

    Keyword arguments:
      df -- Datafeed to apply indicator
      minbars -- Min. number of bars per flip to avoid discarding (default 12)
      bb_period -- Bollinger bands period (default 20)
      bb_dev -- Bollinger bands deviation (default 2.0)
      bb_sma -- List of SMA timeperiod for Bands Width SMA calculation
      nan_value -- Values for zigzag indicator during search phase (default 0.0)
      level -- logging level (default WARN)
    """
    class ActionCtrl():
      class ActionType(Enum):
        NoActions = 0
        SearchingHigh = 1
        SearchingLow = 2
      def __init__(self, high, low, idx, delta, level=logging.WARN):
        self.__logger = logging.getLogger(__name__)
        self.__logger.setLevel(level)
        self.curr = ActionCtrl.ActionType.NoActions
        self.last_high = high
        self.last_high_idx = idx
        self.beforelast_high = high
        self.beforelast_high_idx = idx
        self.last_swing_high_idx = idx
        self.last_low = low
        self.last_low_idx = idx
        self.beforelast_low = low
        self.beforelast_low_idx = idx        
        self.last_swing_low_idx = idx
        self.delta = delta
        self.x = []
        self.y = []
        self.events = ZIGZAG_Events()
        self.__logger.debug('New action at idx={}: last_high={}, last_low={}, min-delta={}'.format(idx, self.last_high, self.last_low, self.delta))

      def __result(self):
        if self.curr == ActionCtrl.ActionType.SearchingHigh:
          return 'high'
        elif self.curr == ActionCtrl.ActionType.SearchingLow:
          return 'low'
        return 'no-action'

      # this function updates MAX|MIN values with last recorded depending on the current action
      def zigzag(self, x, df):
        log = 'Procesing [{}]:'.format(x.name)
        self.events.clear()

        # check if HIGH must be updated
        max_value = x.HIGH #max(x.OPEN,x.CLOSE)
        if self.curr == ActionCtrl.ActionType.SearchingHigh and max_value > self.last_high:
          self.beforelast_high = self.last_high
          self.beforelast_high_idx = self.last_high_idx          
          self.last_high = max_value
          self.last_high_idx = x.name
          log += ' new HIGH={}'.format(max_value)   
          self.__logger.debug(log)
          return self.__result()

        # check if LOW must be updated
        min_value = x.LOW #min(x.OPEN,x.CLOSE)
        if self.curr == ActionCtrl.ActionType.SearchingLow and min_value < self.last_low:
          self.beforelast_low = self.last_low
          self.beforelast_low_idx = self.last_low_idx
          self.last_low = min_value
          self.last_low_idx = x.name
          log += ' new LOW={}'.format(min_value)
          self.__logger.debug(log)
          return self.__result()

        # check if search HIGH starts
        if self.curr != ActionCtrl.ActionType.SearchingHigh and max_value > x.BOLLINGER_HI:
          self.events.ZIGZAG_StartMaxSearch = True
          self.curr = ActionCtrl.ActionType.SearchingHigh
          # check delta condition
          curr_delta = (x.name - self.last_high_idx)
          if curr_delta < self.delta:
            log += ' ERR_DELTA \/ ={}' .format(curr_delta)
            df.at[self.last_high_idx,'ZIGZAG'] =  nan_value
            df.at[self.last_high_idx,'ACTION'] =  'high'
            if max_value > self.last_high:
              log += ' replace_HIGH @[{}]=>{}'.format(self.last_high_idx,max_value)               
              self.last_high = max_value
              self.last_high_idx = x.name
            else:
              log += ' keep_HIGH @[{}]=>{}'.format(self.last_high_idx,self.last_high)
            df.at[self.last_low_idx,'ZIGZAG'] =  nan_value
            df.at[self.last_low_idx,'ACTION'] =  'high' 
            log += ' remove LOW @[{}]'.format(self.last_low_idx)
            self.last_low = self.beforelast_low
            self.last_low_idx = self.beforelast_low_idx
            self.__logger.info(log)  
          else:
            # save last low     
            df.at[self.last_low_idx,'ZIGZAG'] =  self.last_low   
            self.x.append(self.last_low_idx)
            self.y.append(self.last_low)
            # starts high recording
            self.beforelast_high = self.last_high
            self.beforelast_high_idx = self.last_high_idx
            self.last_high = max_value
            self.last_high_idx = x.name
            log += ' save LOW @[{}]={}, new HIGH=>{}'.format(self.last_low_idx, self.last_low, max_value)    
            self.__logger.debug(log)
          return self.__result()

        # check if search LOW starts
        if self.curr != ActionCtrl.ActionType.SearchingLow and min_value < x.BOLLINGER_LO:
          self.events.ZIGZAG_StartMinSearch = True
          self.curr = ActionCtrl.ActionType.SearchingLow
          # check delta condition
          curr_delta = (x.name - self.last_low_idx)
          if curr_delta < self.delta:
            log += ' ERR_DELTA /\ ={}' .format(curr_delta) 
            df.at[self.last_low_idx,'ZIGZAG'] =  nan_value
            df.at[self.last_low_idx,'ACTION'] =  'low'
            if min_value < self.last_low:
              log += ' replace_LOW @[{}]=>{}'.format(self.last_low_idx,min_value)              
              self.last_low = min_value
              self.last_low_idx = x.name  
            else:
              log += ' keep_LOW @[{}]=>{}'.format(self.last_low_idx,self.last_low)
            df.at[self.last_high_idx,'ZIGZAG'] =  nan_value
            df.at[self.last_high_idx,'ACTION'] =  'low' 
            log += ' remove HIGH @[{}]'.format(self.last_high_idx)
            self.last_high = self.beforelast_high
            self.last_high_idx = self.beforelast_high_idx
            self.__logger.info(log)  
          else:
            # save last high
            df.at[self.last_high_idx,'ZIGZAG'] =  self.last_high
            self.x.append(self.last_high_idx)
            self.y.append(self.last_high)
            # starts low recording
            self.beforelast_low = self.last_low
            self.beforelast_low_idx = self.last_low_idx
            self.last_low = min_value
            self.last_low_idx = x.name
            log += ' save HIGH @[{}]={}, new LOW=>{}'.format(self.last_high_idx, self.last_high, min_value)        
            self.__logger.debug(log)
          return self.__result()

        if self.curr == ActionCtrl.ActionType.SearchingLow:
          log += ' curr LOW @[{}]=>{}'.format(self.last_low_idx,self.last_low)
        elif self.curr == ActionCtrl.ActionType.SearchingHigh:
          log += ' curr HIGH @[{}]=>{}'.format(self.last_high_idx,self.last_high)
        self.__logger.debug(log)
        return self.__result()    

    # clear events
    self.__events.clear()

    # copy dataframe and calculate bollinger bands if not yet present
    _df = df.copy()
    _df['BOLLINGER_HI'], _df['BOLLINGER_MA'], _df['BOLLINGER_LO'] = talib.BBANDS(_df.CLOSE, timeperiod=bb_period, nbdevup=bb_dev, nbdevdn=bb_dev, matype=0)
    _df['BOLLINGER_WIDTH'] = _df['BOLLINGER_HI'] - _df['BOLLINGER_LO']
    for sma in bb_sma:
      _df['BOLLINGER_WIDTH_SMA{}'.format(sma)] = talib.SMA(_df['BOLLINGER_WIDTH'], timeperiod=sma)
    boll_b = (_df.CLOSE - _df['BOLLINGER_LO'])/(_df['BOLLINGER_HI'] - _df['BOLLINGER_LO'])
    boll_b[np.isnan(boll_b)]=0.5
    boll_b[np.isinf(boll_b)]=0.5
    _df['BOLLINGER_b'] = boll_b
    _df.dropna(inplace=True)
    _df.reset_index(drop=True, inplace=True)

    # Initially no actions are in progress, record first high and low values creating an ActionCtrl object
    action = ActionCtrl(
              high= _df['HIGH'][0], #max(_df['OPEN'][0], _df['CLOSE'][0]), 
              low = _df['LOW'][0], #min(_df['OPEN'][0], _df['CLOSE'][0]), 
              idx = _df.iloc[0].name, 
              delta= minbars,
              level=level)

    _df['ZIGZAG'] = nan_value
    _df['ACTION'] = 'no-action'
    _df['ACTION'] = _df.apply(lambda x: action.zigzag(x, _df), axis=1)

    # fills last element as pending
    if _df.ZIGZAG.iloc[-1] == nan_value:
      _df.at[_df.index[-1],'ZIGZAG'] =  action.last_high if _df.ACTION.iloc[-1] == 'high' else action.last_low
      _df.at[_df.index[-1],'ACTION'] =  _df.ACTION.iloc[-1] + '-in-progress'
    
    self.__df = _df
    self.__action = action
    return self.__df, self.__action.x, self.__action.y, self.__action.events

  def getDataFrame(self):
    return self.__df