#!/usr/bin/env python
import platform 
import logging
import sys
import os
import sys
import dbus
import dbus.service
if sys.version_info.major == 2:
    import gobject
else:
    from gi.repository import GLib as gobject
import sys
import time
import configparser # for config/ini file
 
# goodwe library and asyncio
import asyncio
import goodwe as goodwe

# our own packages from victron
sys.path.insert(1, os.path.join(os.path.dirname(__file__), '/opt/victronenergy/dbus-systemcalc-py/ext/velib_python'))
from vedbus import VeDbusService

class SystemBus(dbus.bus.BusConnection):
    def __new__(cls):
        return dbus.bus.BusConnection.__new__(cls, dbus.bus.BusConnection.TYPE_SYSTEM)
 
class SessionBus(dbus.bus.BusConnection):
    def __new__(cls):
        return dbus.bus.BusConnection.__new__(cls, dbus.bus.BusConnection.TYPE_SESSION)

class VictronDbusService():
  """ VictronDbusService holds VDbus specific service creation and connection code
  """
  def _dbus_connection(self):
    return SessionBus() if 'DBUS_SESSION_BUS_ADDRESS' in os.environ else SystemBus()
 
  # Here is the bit you need to create multiple new services - try as much as possible timplement the Victron Dbus API requirements.
  def create_dbus_service(self, base, physical, logical, id, instance, product_id, product_name, custom_name, type=None):
      dbus_service =  VeDbusService("{}.{}.{}_id{:02d}".format(base, type, physical,  id), self._dbus_connection())

      # physical is the physical connection
      # logical is the logical connection to align with the numbering of the console display
      # Create the management objects, as specified in the ccgx dbus-api document
      dbus_service.add_path('/Mgmt/ProcessName', __file__)
      dbus_service.add_path('/Mgmt/ProcessVersion', 'Unkown version, and running on Python ' + platform.python_version())
      dbus_service.add_path('/Mgmt/Connection', logical)
  
      # Create the mandatory objects, note these may need to be customised after object creation
      # We're creating a connected object by default
      dbus_service.add_path('/DeviceInstance', instance)
      dbus_service.add_path('/ProductId', product_id)
      dbus_service.add_path('/ProductName', product_name)
      dbus_service.add_path('/CustomName', custom_name)
      dbus_service.add_path('/FirmwareVersion', 0)
      dbus_service.add_path('/HardwareVersion', 0)
      dbus_service.add_path('/Connected', 1, writeable=True) # Mark devices as disconnected until they are confirmed
  
      dbus_service.add_path('/UpdateIndex', 0, writeable=True)
      dbus_service.add_path('/StatusCode', 0, writeable=True)

      # Create device type specific objects
      if type == 'temperature':
          dbus_service.add_path('/Temperature', 0)
          dbus_service.add_path('/Status', 0)
          dbus_service.add_path('/TemperatureType', 0, writeable=True)
      if type == 'humidity':
          dbus_service.add_path('/Humidity', 0)
          dbus_service.add_path('/Status', 0)
  
      return dbus_service

class GoodWeEMService:
  """ GoodWe Inverter and SmartMeter class
  """
  def __init__(self, product_name='GoodWe EM', connection='GoodWe EM service'):
    """Creates a GoodWeEMService object to interact with GoodWe Inverter and SmartMeter, 
    it also handles configuration management and Dbus updates

    Args:
        product_name (str, optional): _description_. Defaults to 'GoodWe EM'.
        connection (str, optional): _description_. Defaults to 'GoodWe EM service'.
    """
    config = self._get_config()

    self.dbus_service = None
    self.custom_name = config['DEFAULT']['CustomName']
    self.product_name = product_name
    self.product_id = 0xFFFF
    self.logical_connection = connection
    self.device_instance = int(config['DEFAULT']['DeviceInstance'])
    self.has_meter = bool(config['ONPREMISE']['HasMeter'])
    self.pv_inverter_position = int(config['ONPREMISE']['Position'])
    self.pv_max_power = int(config['ONPREMISE']['MaxPower'])
    self.pv_host = config['ONPREMISE']['Host']

    if self.has_meter:
      self.meter_product_name = config['SMARTMETER']['ProductName']

    #formatting 
    self._kwh = lambda p, v: (str(round(v, 2)) + 'KWh')
    self._a = lambda p, v: (str(round(v, 1)) + 'A')
    self._w = lambda p, v: (str(round(v, 1)) + 'W')
    self._v = lambda p, v: (str(round(v, 1)) + 'V') 

    logging.debug("%s /DeviceInstance = %d" % (self.custom_name, self.device_instance))

  def set_dbus_service(self, dbus_service):
    self.dbus_service = dbus_service

  def _get_config(self):
    config = configparser.ConfigParser()
    config.read("%s/config.ini" % (os.path.dirname(os.path.realpath(__file__))))
    return config

  async def _get_goodwe_data(self, host):
    # ToDo: Read sensor data unit
    inverter = await goodwe.connect(host)
    meter_data = await inverter.read_runtime_data()
    
    # check for response
    if not meter_data:
        raise ConnectionError("No response from GoodWe EM - %s" % (host))
    
    return meter_data
 
  def _get_goodwe_serial(self):
    # Dummy function to retrieve a "serial" identifier, using custom name for now
    config = self._get_config()
    return config['DEFAULT']['CustomName']

  def refresh_meter_data(self):   
    try:

      #get data from GoodWe EM through Goodwe python library in async
      meter_data = asyncio.run(self._get_goodwe_data(self.pv_host))       
      
      # ppv = for photo voltaic voltage
      self.pv_power = meter_data['ppv']
      # igrid current ac on grid (not differentiated by the meter)
      self.pv_current = meter_data['igrid']
      # total power equals power as GoodWe gives us the aggregatted ammount
      self.pv_total = self.pv_power
      # total voltage on AC line (not differentiated by the meter)
      self.pv_voltage = meter_data['vgrid']

      # Only if we have a smart meter setted up, almost all the values are the same with the exception of house_consumption
      if self.has_meter:
        # ToDo: review and fix -abs, we're negative abs as Victron expects negative values on export
        self.meter_forward = -abs(meter_data['pgrid'])
        # reverse is "sold to the grid"
        self.meter_reverse = -abs(meter_data['pgrid'] - meter_data['house_consumption']) # sold to the grid
        # house consumption is total AC load
        self.meter_house_consumption = meter_data['house_consumption']
        # igrid = AC current, not differentiated by the smart meter
        self.meter_current = meter_data['igrid']
        self.meter_total_power = -abs(meter_data['pgrid'])
        self.meter_voltage = meter_data['vgrid']

    except Exception as e:
      logging.critical('Error at %s', '_update', exc_info=e)
       
    return True
 
  def update_dbus_pv_inverter(self):
    """_summary_
    updates dbus as a callback function, dbus is setted on the GoodWe EM Class
    Returns:
        _type_: _description_
    """
    dbus_service = self.dbus_service
    try:
      self.refresh_meter_data()
      pre = '/Ac/L1'
      #current = power / voltage
      dbus_service['pvinverter'][pre + '/Voltage'] = self.pv_voltage
      dbus_service['pvinverter'][pre + '/Current'] = self.pv_current
      dbus_service['pvinverter'][pre + '/Power'] = self.pv_power
      if self.pv_power > 0:
        dbus_service['pvinverter'][pre + '/Energy/Forward'] = self.pv_total/1000/60 
      else:
        dbus_service['pvinverter'][pre + '/Voltage'] = 0
        dbus_service['pvinverter'][pre + '/Current'] = 0
        dbus_service['pvinverter'][pre + '/Power'] = 0
        dbus_service['pvinverter'][pre + '/Energy/Forward'] = 0
          
      dbus_service['pvinverter']['/Ac/Power'] = dbus_service['pvinverter']['/Ac/L1/Power']
      dbus_service['pvinverter']['/Ac/Energy/Forward'] = dbus_service['pvinverter']['/Ac/L1/Energy/Forward']
      
      # update grid meter only if it's configured
      if self.has_meter:
        if 'grid' in dbus_service:
          logging.debug("Updating meter values")
          pre = '/Ac/L1'
          #current = power / voltage
          dbus_service['grid'][pre + '/Voltage'] = self.meter_voltage
          dbus_service['grid'][pre + '/Current'] = self.meter_current
          dbus_service['grid'][pre + '/Power'] = self.meter_total_power
          
          dbus_service['grid']['/Ac/Energy/Forward'] = self.meter_forward/1000/60 
          dbus_service['grid']['/Ac/Energy/Reverse'] = self.meter_reverse/1000/60 
          dbus_service['grid']['/Ac/L1/Energy/Forward'] = self.meter_forward/1000/60 
          dbus_service['grid']['/Ac/L1/Energy/Reverse'] = self.meter_reverse/1000/60 
          dbus_service['grid']['/Ac/Power'] = self.meter_total_power          

      #logging
      logging.debug("House Consumption (/Ac/Power): %s" % (dbus_service['pvinverter']['/Ac/Power']))
      logging.debug("House Forward (/Ac/Energy/Forward): %s" % (dbus_service['pvinverter']['/Ac/Energy/Forward']))
      logging.debug("---")
      
      # increment UpdateIndex - to show that new data is available
      index = dbus_service['pvinverter']['/UpdateIndex'] + 1  # increment index
      if index > 255:   # maximum value of the index
        index = 0       # overflow from 255 to 0
      dbus_service['pvinverter']['/UpdateIndex'] = index

      #update lastupdate vars
      self._dbus_last_update = time.time()    
    except Exception as e:
      logging.critical('Error at %s', '_update', exc_info=e)

    return True

def main():
  #configure logging
  logging.basicConfig(      format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S',
                            level=logging.INFO,
                            handlers=[
                               	logging.FileHandler("%s/current.log" % (os.path.dirname(os.path.realpath(__file__)))),
                               	logging.StreamHandler()
                            ])

  logging.info("Start")

  from dbus.mainloop.glib import DBusGMainLoop
  # Have a mainloop, so we can send/receive asynchronous calls to and from dbus
  DBusGMainLoop(set_as_default=True)
  
  goodwe_inverter = GoodWeEMService()
  victron_dbus = VictronDbusService()

  try:

      # Dictonary to hold the multiple services as we have two dbus but only one outgoing http connection
      dbusservice = {} # 
 
      # Base dbus path
      base = 'com.victronenergy'

      # creating new dbus service on pvinverter path
      dbusservice['pvinverter'] = victron_dbus.create_dbus_service(base, 'http', goodwe_inverter.logical_connection, 
      goodwe_inverter.device_instance, instance=goodwe_inverter.device_instance, product_id=goodwe_inverter.product_id,
      product_name=goodwe_inverter.product_name, custom_name=goodwe_inverter.custom_name, type="pvinverter"  )

      # add paths specific to pv inverter
      dbusservice['pvinverter'].add_path('/Ac/Energy/Forward', None, writeable=True, gettextcallback = goodwe_inverter._kwh)
      dbusservice['pvinverter'].add_path('/Ac/Power', 0, writeable=True, gettextcallback = goodwe_inverter._w)
      dbusservice['pvinverter'].add_path('/Ac/Current', 0, writeable=True, gettextcallback = goodwe_inverter._a)
      dbusservice['pvinverter'].add_path('/Ac/Voltage', 0, writeable=True, gettextcallback = goodwe_inverter._v)
      dbusservice['pvinverter'].add_path('/Ac/L1/Voltage', 0, writeable=True, gettextcallback = goodwe_inverter._v)
      dbusservice['pvinverter'].add_path('/Ac/L1/Current', 0, writeable=True, gettextcallback = goodwe_inverter._a)
      dbusservice['pvinverter'].add_path('/Ac/L1/Power', 0, writeable=True, gettextcallback = goodwe_inverter._w)
      dbusservice['pvinverter'].add_path('/Ac/L1/Energy/Forward', None, writeable=True, gettextcallback = goodwe_inverter._kwh)
      # Position is required to establish on which line the inverter sits (AC OUT, In, ETC)
      dbusservice['pvinverter'].add_path('/Position', goodwe_inverter.pv_inverter_position, writeable=True)
      dbusservice['pvinverter'].add_path('/MaxPower', goodwe_inverter.pv_max_power, writeable=True)

      # create service for grid meter
      if goodwe_inverter.has_meter:
        dbusservice['grid'] = victron_dbus.create_dbus_service(base, 'http', goodwe_inverter.logical_connection, 
        goodwe_inverter.device_instance, instance=goodwe_inverter.device_instance, product_id=goodwe_inverter.product_id,
        product_name=goodwe_inverter.meter_product_name, custom_name=goodwe_inverter.meter_product_name, type="grid"  )


        dbusservice['grid'].add_path('/Ac/L1/Energy/Forward', None, writeable=True, gettextcallback = goodwe_inverter._kwh)
        dbusservice['grid'].add_path('/Ac/L1/Energy/Reverse', None, writeable=True, gettextcallback = goodwe_inverter._kwh)
        dbusservice['grid'].add_path('/Ac/Energy/Forward', None, writeable=True, gettextcallback = goodwe_inverter._kwh)
        dbusservice['grid'].add_path('/Ac/Energy/Reverse', None, writeable=True, gettextcallback = goodwe_inverter._kwh)
        dbusservice['grid'].add_path('/Ac/Power', 0, writeable=True, gettextcallback = goodwe_inverter._w)
        dbusservice['grid'].add_path('/Ac/L1/Current', 0, writeable=True, gettextcallback = goodwe_inverter._a)
        dbusservice['grid'].add_path('/Ac/L1/Voltage', 0, writeable=True, gettextcallback = goodwe_inverter._v)
        dbusservice['grid'].add_path('/Ac/L1/Power', 0, writeable=True, gettextcallback = goodwe_inverter._w)
        dbusservice['grid'].add_path('/Position', goodwe_inverter.pv_inverter_position, writeable=True)
        

      # pass dbus object to goodwe class
      goodwe_inverter.set_dbus_service(dbusservice)
      # add _update function 'timer'
      # update every 5 seconds to prevent blocking by GoodWe Inverter
      gobject.timeout_add(5000, goodwe_inverter.update_dbus_pv_inverter) # pause 5000ms before the next request

      logging.info('Connected to dbus, and switching over to gobject.MainLoop() (= event based)')
      mainloop = gobject.MainLoop()
      mainloop.run()            
  except Exception as e:
    logging.critical('Error at %s', 'main', exc_info=e)
if __name__ == "__main__":
  main()
