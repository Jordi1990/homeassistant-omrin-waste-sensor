import logging
import requests
import uuid
import json
import datetime
import locale

from homeassistant.helpers import debounce, entity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from homeassistant.const import TEMP_CELSIUS
from homeassistant.helpers.entity import Entity
from rsa import key, common, pkcs1
from Crypto.PublicKey import RSA
from base64 import b64decode, b64encode

CONF_POSTALCODE = 'postalcode'
CONF_HOUSENUMBER = 'housenumber'
CONF_DATEFORMAT = 'dateformat'

_LOGGER = logging.getLogger(__name__)

# Generate unique id
appId = uuid.uuid1().__str__()
#dateFormat = '%Y-%m-%d'
dateFormat = '%a %d %b'

# Post helper method
def doPost(url, data=None, jsonData=None):
    if (data is None):
        request = requests.post(url, json=jsonData)
    else:
        request = requests.post(url, data=data)

    if request.status_code != 200:
        raise requests.RequestException(
            "Request failed with status code {0} and reason {1}".format(request.status_code, request.reason))
    return json.loads(request.text)


# Retrieve public key from API used to sign requests
def fetchPublicKey():
    response = doPost("https://api-omrin.freed.nl//Account/GetToken/",
                      jsonData={'AppId': appId, 'AppVersion': '', 'OsVersion': '', 'Platform': ''})
    return b64decode(response['PublicKey'])


# Retrieve next empty date
def getNextEmptyDate(calendar, type=None):
    if (type is None):
        nextEmptyDate = next(iter(calendar), None)
    else:
        nextEmptyDate = next(filter(lambda x: x["Omschrijving"] == type, calendar), None)
    datetimeObj = datetime.datetime.strptime(nextEmptyDate['Datum'], '%Y-%m-%dT%H:%M:%S')
    _LOGGER.debug(f"Dateformat in getNextEmptyDate: {dateFormat} = {datetimeObj.strftime(dateFormat)}")
    return datetimeObj.strftime(dateFormat)


# Retrieve container type on certain date
def getEmptyTypeOnDate(calendar, date):
    date = date.strftime('%Y-%m-%dT00:00:00')
    emptyEvent = next(filter(lambda x: x["Datum"] == date, calendar), None)
    if emptyEvent is not None:
        return emptyEvent['Omschrijving']
    else:
        return None


# Retrieve calendar for given address
def fetchCalendar(publicKey, postalCode, houseNumber):
    rsaPublicKey = RSA.importKey(publicKey)
    requestBody = {'a': False, 'Email': None, 'Password': None, 'PostalCode': postalCode, 'HouseNumber': houseNumber}

    # Sign request with public key
    encryptedRequest = pkcs1.encrypt(json.dumps(requestBody).encode(),
                                     rsaPublicKey)
    # Encode request
    base64EncodedRequest = b64encode(encryptedRequest).decode("utf-8")

    response = doPost("https://api-omrin.freed.nl//Account/FetchAccount/" + appId,
                      data='"' + base64EncodedRequest + '"')

    return response['CalendarHomeV2']

def parseCalendar(calendar):
    nextBiobak = getNextEmptyDate(calendar, 'Biobak')
    nextSortibak = getNextEmptyDate(calendar, 'Sortibak')
    nextPapierbak = getNextEmptyDate(calendar, 'Papierbak')
    typeToEmptyToday = getEmptyTypeOnDate(calendar, datetime.datetime.now())
    typeToEmptyTomorrow = getEmptyTypeOnDate(calendar, datetime.datetime.now() + datetime.timedelta(days=1))
    nextEmptyDate = getNextEmptyDate(calendar)
    typeToEmptyNext = getEmptyTypeOnDate(calendar, datetime.datetime.strptime(nextEmptyDate, dateFormat))

    return {'biobak': nextBiobak, 'sortibak': nextSortibak, 'papierbak': nextPapierbak, 'today': typeToEmptyToday,
            'tomorrow': typeToEmptyTomorrow, 'nextdate': nextEmptyDate, 'next': typeToEmptyNext}


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    _LOGGER.debug("Setting omrin waste sensor")
    dateFormat = config.get(CONF_DATEFORMAT)
    _LOGGER.debug(f"dateFormat: {dateFormat}")
    publicKey = await hass.async_add_executor_job(fetchPublicKey)

    async def async_update_data():
        try:
            postalcode = config.get(CONF_POSTALCODE)
            housenumber = config.get(CONF_HOUSENUMBER)
            # Run fetchCalendar async
            calendar = await hass.async_add_executor_job(fetchCalendar, publicKey, postalcode, housenumber)
            # TODO: Only run parse calendar every hour and fetch calendar once a day
            return await hass.async_add_executor_job(parseCalendar, calendar)
        except requests.RequestException:
            raise UpdateFailed

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="sensor",
        update_method=async_update_data,
        update_interval=datetime.timedelta(hours=1)        
    )

    types = [{'type':'biobak',  'friendlyName': 'GFT'}, {'type': 'sortibak', 'friendlyName': 'Restafval'}, {'type':'papierbak', 'friendlyName': 'Papier'}, {'type': 'today', 'friendlyName': 'Vandaag'}, {'type':'tomorrow', 'friendlyName': 'Morgen'}, {'type':'nextdate', 'friendlyName': 'Volgende datum'}, {'type':'next', 'friendlyName': 'Volgende'}]

    # Fetch initial data
    await coordinator.async_refresh()

    async_add_entities(WasteEmptyDateSensor(coordinator, type['type'], type['friendlyName']) for idx, type
                       in enumerate(types))


class WasteEmptyDateSensor(Entity):
    _state = None

    def __init__(self, coordinator, type, friendlyName):
        self.coordinator = coordinator
        self._type = type
        self._name = f'omrin_{type}'
        self._unique_id = self._name

    @property
    def name(self):
        return self._name

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def state(self):
        return self.coordinator.data[self._type]

    @property
    def device_state_attributes(self):
        """Return attributes for the sensor."""
        if self._type == "biobak" or self._type == "sortibak" or self._type == "papierbak":
            stateDateTime = datetime.datetime.strptime(self.coordinator.data[self._type], dateFormat)
            return {'timestamp': datetime.datetime.timestamp(stateDateTime)}
        else:
            return {}

    @property
    def should_poll(self):
        """No need to poll. Coordinator notifies entity of updates."""
        return False

    async def async_update(self):
        await self.coordinator.async_request_refresh()

    async def async_added_to_hass(self):
        self.coordinator.async_add_listener(
            self.async_write_ha_state
        )

    async def async_will_remove_from_hass(self):
        self.coordinator.async_remove_listener(
            self.async_write_ha_state
        )
