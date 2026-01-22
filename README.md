# Power Curve Profiles for Home Assistant

## Overview
Power Curve Profiles is a custom Home Assistant integration that learns how much energy a device uses over time and combines that with dynamic electricity prices to calculate what it would cost to run the device at every possible start time of the day.

It is especially useful for households with dynamic energy contracts such as Tibber, where electricity prices vary throughout the day.

---

## What problem does this solve
Most energy optimizations assume a fixed power draw or a fixed runtime. Real household devices do not behave like that.

Examples
- A dishwasher heats water, then idles, then heats again
- A washing machine has short high power bursts
- A dryer can dramatically extend runtime and energy usage

This integration
- Learns the real energy usage curve of a device
- Averages multiple runs for higher accuracy
- Projects the real cost of running the device at any moment today or tomorrow

---

## Core concept
The integration works in two independent layers.

### Learning layer, power curve
- Uses a power sensor reporting watts W
- Detects when the device starts and stops automatically
- Integrates power continuously based on sensor state changes
- Stores energy usage in 5 minute buckets expressed in kWh
- Averages multiple runs over time

This produces a highly accurate real world energy usage curve.

### Pricing layer, cost projection
- Uses a dynamic electricity price sensor
- Applies the learned curve to electricity prices
- Calculates the total cost if the device were started at every 15 minute interval
- Generates 96 possible start cost values per day

The device does not need to run for prices to update.

---

## Example
If a dishwasher has this average energy profile expressed as 5 minute buckets in kWh

```
[0.05, 0.15, 0.00, 0.06, 0.16]
```

And electricity prices vary throughout the day, the integration answers
- What would it cost if I start at 08:15
- What about 11:30
- Or 22:45

This calculation is performed for every quarter of the day.

---

## Requirements

### Power sensor, required
You need a sensor that reports instantaneous power usage in watts W.

Typical sources
- Smart plugs
- Energy monitoring clamps
- Shelly, ESPHome, Zigbee, or Z Wave devices

---

### Price sensor, optional but recommended
The integration is designed to work with Tibber style price sensors.

Typical example
- sensor.tibber_prices

The sensor state itself is usually ok or unavailable, but the attributes expose the price timeline.

Expected attribute structure

```
today:
  - total: 0.2394
    startsAt: "2026-01-22T00:00:00+01:00"
tomorrow:
  - total: 0.2526
    startsAt: "2026-01-23T00:00:00+01:00"
```

Notes
- Prices must be in currency per kWh, for example EUR per kWh
- Hourly prices are automatically expanded to 15 minute slots
- Native 15 minute prices are supported directly

---

## Installation

1. Copy this repository to

```
config/custom_components/power_curve_profiles/
```

2. Restart Home Assistant

3. Go to Settings, Devices and Services, Add Integration

4. Search for Power Curve Profiles

---

## Configuration
Each configured device creates one sensor entity.

### Required settings
- Power sensor
- Standby power W  
  Below this value the device is considered idle
- Wait time seconds  
  Time the power must remain below standby to end a run

### Optional settings
- Expected runtime seconds  
  Hard cutoff for shorter cycles, useful for devices with multiple operating modes
- Price sensor  

sensor:
  - platform: rest
    name: Tibber prices 15m
    resource: https://api.tibber.com/v1-beta/gql
    method: POST
    scan_interval: 900   # 15 minutes
    payload: >
      {
        "query": "{ viewer { homes { currentSubscription { priceInfo(resolution: QUARTER_HOURLY) { today { total startsAt } tomorrow { total startsAt } }}}}"
      }
    json_attributes_path: "$.data.viewer.homes[0].currentSubscription.priceInfo"
    json_attributes:
      - today
      - tomorrow
    value_template: "ok"
    headers:
      Authorization: "Bearer YOUR_TIBBER_API_TOKEN"
      Content-Type: application/json
      User-Agent: HomeAssistant




You can add the same power sensor multiple times with different settings.

Example use case
- One tracker with a 2 hour cutoff for wash only
- One tracker without cutoff for wash plus dry

---

## How it works internally

### Run detection
A run starts when the power sensor rises above the configured standby power.

### High accuracy energy integration
Each power sensor update is treated as a constant power segment until the next update.

Energy is calculated as

```
energy_kWh = power_W * seconds / 3_600_000
```

This avoids missing short heating or motor bursts.

---

## If the device is not used
- The learned power curve remains unchanged
- Electricity prices continue to update daily
- Cost projections stay accurate

The device does not need to run every day.

---

## Deleting an entry
Removing an integration entry removes the sensor and its stored curve data.
Re adding the device starts with a fresh profile.

---

## Intended use
This integration was created for personal use to
- Understand real device energy behavior
- Optimize start times with dynamic electricity prices
- Serve as a foundation for future automations

---

## Support notice
This project was created for personal use.

No support is currently provided.
No guarantees are made.
Use at your own risk.
