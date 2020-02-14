import logging
import requests
import uuid
import json
import datetime

from homeassistant.helpers import debounce, entity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from homeassistant.const import TEMP_CELSIUS
from homeassistant.helpers.entity import Entity
from rsa import key, common, pkcs1
from Crypto.PublicKey import RSA
from base64 import b64decode, b64encode

REQUEST_REFRESH_DEFAULT_COOLDOWN = 10
REQUEST_REFRESH_DEFAULT_IMMEDIATE = True

CONF_POSTALCODE = 'postalcode'
CONF_HOUSENUMBER = 'housenumber'

_LOGGER = logging.getLogger(__name__)

# Generate unique id
appId = uuid.uuid1().__str__()

# Post helper method
def doPost(url, data):
    request = requests.post(url, data)
    if request.status_code != 200:
        raise RequestException("Request failed with status code {0} and reason {1}".format(request.status_code, request.reason))
    return json.loads(request.text)

# Retrieve public key from API used to sign requests
def fetchPublicKey():
    response = doPost("https://api-omrin.freed.nl//Account/GetToken/", json={'AppId': appId, 'AppVersion': '', 'OsVersion': '', 'Platform': ''})
    return b64decode(response['PublicKey'])

# Retrieve calendar for given address
def fetchCalendar(publicKey, postalCode, houseNumber):
    rsaPublicKey = RSA.importKey(publicKey)
    requestBody = {'a': False, 'Email': None, 'Password': None, 'PostalCode': postalCode, 'HouseNumber': houseNumber}

    # Sign request with public key
    encryptedRequest = pkcs1.encrypt(json.dumps(requestBody).encode(),
        rsaPublicKey)
    # Encode request
    base64EncodedRequest = b64encode(encryptedRequest).decode("utf-8")

    response = doPost("https://api-omrin.freed.nl//Account/FetchAccount/" + appId, '"' + base64EncodedRequest + '"')   
    return response['CalendarHomeV2']

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
     _LOGGER.debug("Setting omrin waste sensor")
     publicKey = await hass.async_add_executor_job(fetchPublicKey)

     async def async_update_data():
        try:            
            postalcode = config.get(CONF_POSTALCODE)
            housenumber = config.get(CONF_HOUSENUMBER)

            # Run fetchCalendar async
            return await hass.async_add_executor_job(fetchCalendar, publicKey, postalcode, housenumber)
        except ApiError:
            raise UpdateFailed

     coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="sensor",
        update_method=async_update_data,
        update_interval=datetime.timedelta(hours=12),
        request_refresh_debouncer=debounce.Debouncer(
                hass,
                _LOGGER,
                REQUEST_REFRESH_DEFAULT_COOLDOWN,
                REQUEST_REFRESH_DEFAULT_IMMEDIATE,
            )
     )

     # Fetch initial data
     await coordinator.async_refresh()

     async_add_entities(WasteEmptyDateSensor(coordinator, ent['Omschrijving']) for idx, ent
                       in enumerate(coordinator.data))


class WasteEmptyDateSensor(Entity):
    def __init__(self, coordinator, type):
        self.coordinator = coordinator
        self._type = type
        self._name = f'omrin_{type}'

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        nextDateToEmpty = next(filter(lambda x:x["Omschrijving"]==self._type, self.coordinator.data), None)
        datetimeObj = datetime.datetime.strptime(nextDateToEmpty['Datum'], '%Y-%m-%dT%H:%M:%S')
        return datetimeObj.strftime('%Y-%m-%d')

    @property
    def device_class(self):
        return 'timestamp'

    @property
    def should_poll(self):
        """No need to poll. Coordinator notifies entity of updates."""
        return False

    async def async_update(self):
        await self.coordinator.async_request_refresh()