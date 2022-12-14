# dbus-goodwe-em-pvinverter
Integrate GoodWe EM into Victron Energies Venus OS

## Purpose
With the scripts in this repo it should be easy possible to install, uninstall, restart a service that connects the goodwe-em to the VenusOS and GX devices from Victron.
Idea is inspired on @dbus-shelly-1pm-pvinverter project linked below.

This project is based in the code for Shelly 1PM from Fabian Lauer
- https://github.com/fabian-lauer/dbus-shelly-1pm-pvinverter
- https://github.com/victronenergy/venus/wiki/dbus#pv-inverters

## How it works
Using the GoodWe library it connects to the local installation to gather required sensor data

### ToDo
There are several things but the most important will be to fix the async calls and the sensor units

### My setup
- 1-Phase installation with power clamp
- Venus OS on Raspberry PI 2 4GB version 1.1 - Firmware v2.84
  - No other devices from Victron connected
  - Connected to Wifi netowrk "A"

### Details / Process

## Install & Configuration
### Get the code
Goodwe library is required, for this I recommend the usage of pip (for now) to install it `opkg install python3-pip`

GoodWe requires dataclasses, in Venus OS it resides within python3-modules `opkg install python3-modules`

GoodWe module `pip3 install goodwe`

Grab a copy of this repo and copy into your fata folder ex: `/data/`  `/data/dbus-goodwe-em-pvinverter`.
After that call the install.sh script.

The following script should do everything for you:
```
wget https://github.com/jxoir/dbus-goodwe-em-pvinverter/archive/refs/heads/main.zip
unzip main.zip "dbus-goodwe-em-pvinverter-main/*" -d /data
mv /data/dbus-goodwe-em-pvinverter-main /data/dbus-goodwe-em-pvinverter
chmod a+x /data/dbus-goodwe-em-pvinverter/install.sh
/data/dbus-goodwe-em-pvinverter/install.sh
rm main.zip
```
⚠️ Check configuration after that - because service is already installed an running and with wrong connection data (host, username, pwd) you will spam the log-file

### Change config.ini
Within the project there is a file `/data/dbus-goodwe-em-pvinverter/config.ini` - just change the values - most important is the deviceinstance, custom name and phase under "DEFAULT" and host, username and password in section "ONPREMISE". More details below:

| Section  | Config vlaue | Explanation |
| ------------- | ------------- | ------------- |
| DEFAULT  | AccessType | Fixed value 'OnPremise' |
| DEFAULT  | Deviceinstance | Unique ID identifying the goodwe-em in Venus OS |
| DEFAULT  | CustomName | Name shown in Remote Console (e.g. name of pv inverter) |
| ONPREMISE  | Host | IP or hostname of on-premise goodwe-em web-interface |
| ONPREMISE  | Position | 0=AC input 1; 1=AC output; 2=AC input 2 |
| ONPREMISE  | MaxPower | Max rated power (in Watts) of the inverter |
| ONPREMISE  | HasMeter | 0 or 1 (false or true), use it when you have a smartmeter connected to the inverter |
| SMARTMETER  | ProductName | Name shown in Remote Console (e.g. name of pv inverter) |

## Used documentation
- https://github.com/victronenergy/venus/wiki/dbus#pv-inverters   DBus paths for Victron namespace
- https://github.com/victronenergy/venus/wiki/dbus-api   DBus API from Victron
- https://www.victronenergy.com/live/ccgx:root_access   How to get root access on GX device/Venus OS
