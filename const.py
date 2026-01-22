DOMAIN = "power_curve_profiles"

CONF_POWER_ENTITY = "power_entity"
CONF_STANDBY_W = "standby_w"
CONF_WAIT_TIME_S = "wait_time_s"
CONF_NAME = "name"
CONF_EXPECTED_RUNTIME_S = "expected_runtime_s"

# Optional, price entity like sensor.tibber_prices
CONF_PRICE_ENTITY = "price_entity"

BUCKET_MINUTES = 5
BUCKET_SECONDS = BUCKET_MINUTES * 60

STORAGE_VERSION = 2
STORAGE_KEY_PREFIX = f"{DOMAIN}_"
