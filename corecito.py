#!/usr/bin/env python3
import asyncio
import time
import logging
import yaml
import sys
import traceback
from os.path import exists
from corecito_account import CorecitoAccount

async def main():
  config = get_config()
  logger = setupLogger('logfile-' + config['corecito_exchange'] + '.log')

  #account = Client(api_key=config['binance_api_key'], api_secret=config['binance_api_secret'])
  account = CorecitoAccount(config=config)
  logger.info(f'Working on {account.exchange.capitalize()} Exchange\n')
  #core_number = config['core_number']
  #pair = config['binance_trading_pair']
  #base_currency = config['base_currency']
  #core_number_currency = config['core_number_currency']

  iteration = 0

  while True:
    try:
      iteration += 1
      print(f'------------ Iteration {iteration} ------------')
      # Get BTC/ETH ticker info
      #tickers = account.get_orderbook_tickers()
      # Example Binance {'symbol': 'ETHBTC', 'bidPrice': '0.02706800', 'bidQty': '7.30000000', 'askPrice': '0.02707300', 'askQty': '24.00000000'} # Bid == BUY, ask == SELL
      ticker = await account.get_tickers()
      buy_price = float(ticker["buy_price"])
      sell_price = float(ticker["sell_price"])
      logger.info(f'\nMarket {account.pair}\nbuy price: {buy_price} - sell price: {sell_price}\n')

      # Get my base and Core Number currency balances
      balances = await account.get_balances()
      #base_currency_balance = account.get_asset_balance(asset=base_currency)
      #base_currency_available = float(base_currency_balance["free"])
      # EXAMPLE BTC_balance:Balance(total=0.04140678, available=3.243e-05, in_orders=0.04137435, in_stake=0, coin=Coin(name='BTC'))
      # Get my Core Number currency balance
      #core_number_currency_balance = account.get_asset_balance(asset=core_number_currency)

      logger.info(f"Balances\n(Base) {account.base_currency} balance:{balances['base_currency_balance']} \n(Core) {account.core_number_currency} balance:{balances['core_number_currency_balance']}\n")


      ###########################
      # Core Number Adjustments #
      ###########################
      deviated_core_number = balances['base_currency_available'] / buy_price
      logger.info(f'Core number adjustments')
      logger.info(f'Core number: {account.core_number} {account.core_number_currency}')
      logger.info(f'Deviated Core number:{deviated_core_number:.6f} {account.core_number_currency}')
      excess = round(deviated_core_number - account.core_number, account.max_decimals_buy)
      increase_percentage = excess * 100 / account.core_number
      missing = round(account.core_number - deviated_core_number, account.max_decimals_sell)
      decrease_percentage = missing * 100 / account.core_number

      if coreNumberExploded(account.core_number, deviated_core_number, account.max_core_number_increase_percentage):
        logger.info(f'> Exploded {increase_percentage:.2f}%\nConsider updating CoreNumber to {deviated_core_number:.6f}')

      elif coreNumberIncreased(account.core_number, deviated_core_number, account.min_core_number_increase_percentage, account.max_core_number_increase_percentage):
        logger.info(f'Increased {increase_percentage:.2f}% - excess of {excess:.6f} {account.core_number_currency} denominated in {account.base_currency}')
        tx_result = round(excess * buy_price, account.max_decimals_buy)
        logger.info(f'\n\n>>> Selling: {tx_result:.6f} {account.base_currency} at {buy_price} to park an excess of {excess:.6f} {account.core_number_currency}\n')
        # Sell excess of base currency ie. => in ETH_BTC pair, sell excess BTC => Buy ETH
        if (not config['safe_mode_on']):
          await account.order_market_buy(quantity=excess)
          #account.order_market_buy(symbol=pair, quantity=excess)

      elif coreNumberDecreased(account.core_number, deviated_core_number, account.min_core_number_decrease_percentage, account.max_core_number_decrease_percentage):
        logger.info(f'Decreased {decrease_percentage:.2f}% - missing {missing:.6f} {account.core_number_currency} denominated in {account.base_currency}')
        tx_result = missing * sell_price
        logger.info(f'\n\n>>> Buying: {tx_result:.6f} {account.base_currency} at {buy_price} taking {missing:.6f} {account.core_number_currency} from reserves\n')
        # Buy missing base currency; ie. => in ETH_BTC pair, buy missing BTC => Sell ETH
        if (not config['safe_mode_on']):
          await account.order_market_sell(quantity=missing)
          #account.order_market_sell(symbol=pair, quantity=missing)

      elif coreNumberPlummeted(account.core_number, deviated_core_number, account.max_core_number_decrease_percentage):
        logger.info(f'> Plummeted {decrease_percentage:.2f}%\nConsider updating CoreNumber to {deviated_core_number:.6f}')

      else:
        logger.info(f'> Price is rock-solid stable ({increase_percentage:.2f}%)')

      # Update balances after adjusting to core number
      balances = await account.get_balances()
      logger.info(f"Final {account.base_currency} available:{balances['base_currency_available']} - {account.core_number_currency} available:{balances['core_number_currency_available']}")

      # Loop end
      print(f'------------ Iteration {iteration} ------------\n')
      if config['test_mode_on']:
        await asyncio.sleep(1)
        break
      else:
        # Wait given seconds until next poll
        logger.info("Waiting for next iteration... ({} seconds)\n\n\n".format(config['seconds_between_iterations']))
        await asyncio.sleep(config['seconds_between_iterations'])

    except Exception as e:
      # Network issue(s) occurred (most probably). Jumping to next iteration
      if config['test_mode_on']:
        logger.info("Exception occurred -> '{}'.\n\n\n".format(e))
        print(traceback.format_exc())
        await asyncio.sleep(1)
        break
      else:
        logger.info("Exception occurred -> '{}'. Waiting for next iteration... ({} seconds)\n\n\n".format(e, config['seconds_between_iterations']))
        print(traceback.format_exc())
        await asyncio.sleep(config['seconds_between_iterations'])

def get_config():
  config_path = "config/default_config.yaml"
  if exists("config/user_config.yaml"):
    config_path = "config/user_config.yaml"
    print('\n\nDetected user configuration...\n')
  else:
    print('Loading default configuration...')
  config_file = open(config_path)
  data = yaml.load(config_file, Loader=yaml.FullLoader)
  config_file.close()
  if data['corecito_exchange'] == 'crypto.com':
    check_config(data)
  return data

def check_config(data):
  try:
    eval('cro.pairs.' + data['cryptocom_trading_pair'])
  except AttributeError:
    print('Trading pair "{}" does not exist (check your config_file)'.format(data['cryptocom_trading_pair']))
    sys.exit(1)
  try:
    eval('cro.coins.' + data['cryptocom_core_number_currency'])
  except AttributeError:
    print('Currency "{}" does not exist (check your config_file)'.format(data['cryptocom_core_number_currency']))
    sys.exit(1)
  try:
    eval('cro.coins.' + data['cryptocom_base_currency'])
  except AttributeError:
    print('Currency "{}" does not exist (check your config_file)'.format(data['cryptocom_base_currency']))
    sys.exit(1)

def coreNumberIncreased(core_number, deviated_core_number, min_core_number_increase_percentage, max_core_number_increase_percentage):
  min_core_number_increase = core_number * (1 + (min_core_number_increase_percentage/100))
  max_core_number_increase = core_number * (1 + (max_core_number_increase_percentage/100))
  return deviated_core_number >= min_core_number_increase and deviated_core_number <= max_core_number_increase

def coreNumberExploded(core_number, deviated_core_number, max_core_number_increase_percentage):
  max_core_number_increase = core_number * (1 + (max_core_number_increase_percentage/100))
  return deviated_core_number > max_core_number_increase

def coreNumberDecreased(core_number, deviated_core_number, min_core_number_decrease_percentage, max_core_number_decrease_percentage):
  min_core_number_decrease = core_number * (1 - (min_core_number_decrease_percentage/100))
  max_core_number_decrease = core_number * (1 - (max_core_number_decrease_percentage/100))
  return deviated_core_number <= min_core_number_decrease and deviated_core_number >= max_core_number_decrease

def coreNumberPlummeted(core_number, deviated_core_number, max_core_number_decrease_percentage):
  max_core_number_decrease = core_number * (1 - (max_core_number_decrease_percentage/100))
  return deviated_core_number < max_core_number_decrease

def setupLogger(log_filename):
  logger = logging.getLogger('CN')

  file_log_handler = logging.FileHandler(log_filename)
  logger.addHandler(file_log_handler)

  stderr_log_handler = logging.StreamHandler()
  logger.addHandler(stderr_log_handler)

  # nice output format
  formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
  file_log_handler.setFormatter(formatter)
  stderr_log_handler.setFormatter(formatter)

  logger.setLevel('DEBUG')
  return logger



loop = asyncio.get_event_loop()
try:
  loop.run_until_complete(main())
except KeyboardInterrupt:
  pass
finally:
  print("Stopping Corecito...")
  loop.close()
