# Omrin waste sensor

Provides sensors for Dutch waste collector Omrin.


### MANUAL INSTALLATION
1. Download the
   [latest release](https://github.com/Jordi1990/homeassistant-omrin-waste-sensor/releases/latest).
2. Unpack the release and copy the `custom_components/omrin_waste` directory
   into the `custom_components` directory of your Home Assistant
   installation.
3. Configure the `omrin_waste` sensor.
4. Restart Home Assistant.

### INSTALLATION VIA Home Assistant Community Store (HACS)
1. Ensure that [HACS](https://hacs.xyz/) is installed.
2. Search for and install the "Omrin waste sensor" integration.
3. Configure the `omrin_waste` sensor.
4. Restart Home Assistant.

## Example config

```Configuration.yaml:
sensor:
  - platform: omrin_waste
    postalcode: 3262CD
    housenumber: 5
```

### CONFIGURATION PARAMETERS
#### SENSOR PARAMETERS
|Attribute |Optional|Description
|:----------|----------|------------
| `postalcode` | No | Postalcode
| `housenumber` | No | Housenumber