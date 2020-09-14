# -*- coding: utf-8 -*-
"""
Created on Fri Sep 11 10:55:20 2020
Title: BackTrader Guide
@author: Wen Jun
"""

import backtrader as bt
import datetime # For datetime objects



# Create a custom datafeed from csv
class customCSV(bt.feeds.GenericCSVData):
    params = (
        ('fromdate', datetime.datetime(2000, 1, 1)),
        ('todate', datetime.datetime(2020, 8, 31)),
        ('dtformat', '%Y-%m-%d'),
        
        ('datetime', 0), #index column
        ('open', 1),
        ('high', 2),
        ('low', 3),
        ('close', 4),
        ('volume', 5),
        ('openinterest', -1), #did not import this column
        
        )

class FixedPerc(bt.Sizer):
    '''This sizer simply returns a fixed size for any operation

    Params:
      - ``perc`` (default: ``0.20``) Perc of cash to allocate for operation
      - ``margin`` (default : 5000) Margin per lot
    '''
    params = (
        ('perc', 0.01),
        ('margin', 5000) # margin per lot
        )
    
    def _getsizing(self, comminfo, cash, data, isbuy):
        cashtouse = self.p.perc * cash
        size = cashtouse // self.p.margin
        
        return size

# Donchian Channel Indicator
class DonchianChannels(bt.Indicator):
    '''
    Params Note:
      - ``lookback`` (default: -1)

        If `-1`, the bars to consider will start 1 bar in the past and the
        current high/low may break through the channel.

        If `0`, the current prices will be considered for the Donchian
        Channel. This means that the price will **NEVER** break through the
        upper/lower channel bands.
    '''

    alias = ('DCH', 'DonchianChannel',)

    lines = ('dcm', 'dch', 'dcl',)  # dc middle, dc high, dc low
    params = dict(
        period=20,
        lookback=-1,  # consider current bar or not
    )

    plotinfo = dict(subplot=False)  # plot along with data
    plotlines = dict(
        dcm=dict(ls='--'),  # dashed line
        dch=dict(_samecolor=True),  # use same color as prev line (dcm)
        dcl=dict(_samecolor=True),  # use same color as prev line (dch)
    )

    def __init__(self):
        hi, lo = self.data.high, self.data.low
        if self.p.lookback:  # move backwards as needed
            hi, lo = hi(self.p.lookback), lo(self.p.lookback)

        self.l.dch = bt.ind.Highest(hi, period=self.p.period)
        self.l.dcl = bt.ind.Lowest(lo, period=self.p.period)
        self.l.dcm = (self.l.dch + self.l.dcl) / 2.0  # avg of the above


# Create a Strategy
class TurtleStrategy(bt.Strategy):
    
    # Set the parameters
    params = (
        ('fast_ema_period', 25),
        ('slow_ema_period', 350),
        ('donchian_period', 20),
        ('ATR_period', 20),
        ('ATR_dist', 2.0)
        )
    
    def log(self, txt, dt = None):
        ''' Logging Function for this strategy'''
        dt = dt or self.datas[0].datetime.date(0)
        print('%s, %s' % (dt.isoformat(), txt))
    
    def __init__(self):
        # Keep a reference to the 'Close' line in the data[0] dataseries
        self.dataclose = self.data.close[0]
        
        # Set up the indicators
        self.emafast = bt.indicators.ExponentialMovingAverage(self.data,
            period = self.p.fast_ema_period)
        self.emaslow = bt.indicators.ExponentialMovingAverage(self.data,
            period = self.p.slow_ema_period)
        self.donchian = DonchianChannels()
        self.atr = bt.indicators.ATR(self.data,
                                     period=self.p.ATR_period)
        
        # Keep track of pending order + price + commission
        self.order = None 
        self.buyprice = None
        self.buycomm = None
        
    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            # Buy/Sell order submitted/accepted by broker. Do nothing
            return 
        
        #Check if order has been completed
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(
                    'LONG EXECUTED, Price: %.2f, Cost: %.2f, Comm: %.2f' % 
                    (order.executed.price,
                     order.executed.value,
                     order.executed.comm))
                
                self.buyprice = order.executed.price
                self.buycomm = order.executed.comm
            
            else: # Sell
                self.log(
                    'SHORT EXECUTED, Price: %.2f, Cost: %.2f, Comm: %.2f' % 
                    (order.executed.price,
                     order.executed.value,
                     order.executed.comm))
                
            self.bar_executed = len(self)
            
            
            
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('Order Canceled/Margin/Rejected')
            
        
        self.order = None
        
    def notify_trade(self, trade):
        if not trade.isclosed:
            return
        
        # open position PnL
        self.log('OPERATION PROFIT, Gross %.2f, Net %.2f' %
                 (trade.pnl, trade.pnlcomm))
                

    def next(self):
        # Log closing price for reference
        self.log('Close, %.2f' % self.dataclose)
        
        # Check if an order is pending, if yes then we do nothing
        if self.order:
            return
        
        # set up parameters for SL and TP
        pdist = self.atr[0] * self.p.ATR_dist
        long_stop = self.dataclose - pdist
        short_stop = self.dataclose + pdist
        long_profit = self.dataclose + pdist
        short_profit = self.dataclose - pdist
        
        # Check if we are in the market
        if not self.position: # not in the market
            # Trade Logic
            if self.dataclose > self.donchian.dch[0]:
                if self.emafast[0] > self.emaslow[0]:
                    # Place BUY trade : 1% of portfolio value
                    self.log('BUY CREATE, %.2f' % self.dataclose)
                    self.buy()
                    
            
            elif self.dataclose < self.donchian.dcl[0]:
                if self.emafast[0] < self.emaslow[0]:
                    # Place SELL trade : 1% of portfolio value
                    self.log('SELL CREATE, %.2f' % self.dataclose)
                    self.sell()
                    

                    
        else: # in the market
            if self.position.size > 0: # For Long position
                if self.dataclose < long_stop or self.dataclose > long_profit:
                    self.close()
            elif self.position.size < 0: # For short position
                if self.dataclose > short_stop or self.dataclose < short_profit:
                    self.close()
            else:
                return
                

# Setting the Cash

if __name__ == '__main__':
    
    # Create a cerebro entity
    cerebro = bt.Cerebro()
    
    # Add a strategy
    cerebro.addstrategy(TurtleStrategy)
    
    # Create a data feed
    data = customCSV(dataname = 'CrudeDaily.csv')
    
    # Add the data feed to cerebro
    cerebro.adddata(data)
    
    # Set our desired cash start
    cerebro.broker.setcash(500000.0)
    
    # Add a sizer according to stake
    cerebro.addsizer(FixedPerc)

    # Set the commission 
    cerebro.broker.setcommission(commission = 5.0, margin = 5000.0)
    
    # Print out the starting conditions
    print('Starting Portfolio Value: %.2f' % cerebro.broker.getvalue())

    # Run over everything
    cerebro.run()

    # Print out the final result
    print('Final Portfolio Value: %.2f' % cerebro.broker.getvalue())
    

