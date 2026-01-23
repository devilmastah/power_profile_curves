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
```
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
```



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

## Graph the result

```
type: custom:apexcharts-card
header:
  show: true
  title: Vaatwasser run cost
graph_span: 48h
update_interval: 15min
span:
  start: day
now:
  show: true
  label: now
apex_config:
  chart:
    height: 260
    width: 100%
  xaxis:
    type: datetime
    labels:
      format: HH:mm
  yaxis:
    min: 0
    decimalsInFloat: 2
    forceNiceScale: false
series:
  - name: Price
    entity: sensor.dishwasher_power_curve
    type: column
    data_generator: >-
      function parseList(v) {
        var out = [];
        if (v === null || v === undefined) return out;

        if (Array.isArray(v)) {
          for (var i = 0; i < v.length; i++) {
            var nArr = Number(v[i]);
            out.push(isFinite(nArr) ? nArr : null);
          }
          return out;
        }

        if (typeof v === "string") {
          var parts = v.split(",");
          for (var j = 0; j < parts.length; j++) {
            var t = parts[j].trim();
            if (t === "" || t.toLowerCase() === "unknown") {
              out.push(null);
            } else {
              var nStr = Number(t);
              out.push(isFinite(nStr) ? nStr : null);
            }
          }
          return out;
        }

        var n = Number(v);
        if (isFinite(n)) out.push(n);
        return out;
      }


      var today = parseList(entity.attributes.start_cost_today_4dp);

      var tomorrow = parseList(entity.attributes.start_cost_tomorrow_4dp);

      var all = today.concat(tomorrow);


      var needed = 48 * 4;

      if (all.length > needed) all = all.slice(0, needed);

      while (all.length < needed) all.push(null);


      var ironbowPalette = [
        [0,0,30],[0,0,35],[0,0,41],[0,0,46],[0,0,51],[0,0,56],[0,0,61],[0,0,65],[0,0,70],[0,1,74],
        [0,1,79],[0,1,83],[3,1,87],[6,1,91],[10,1,95],[13,1,98],[16,1,102],[19,1,105],[23,1,109],[26,1,112],
        [29,1,115],[32,0,118],[35,0,121],[38,0,124],[41,0,127],[44,0,129],[47,0,132],[50,0,134],[53,0,136],[56,0,139],
        [59,0,141],[62,0,143],[65,0,144],[67,0,146],[70,0,148],[73,0,150],[76,0,151],[78,0,153],[81,0,154],[83,0,155],
        [86,0,156],[89,0,157],[91,0,158],[94,0,159],[96,0,160],[99,0,161],[101,0,162],[104,0,162],[106,0,163],[108,0,163],
        [111,0,163],[113,0,164],[115,0,164],[118,0,164],[120,0,164],[122,0,164],[124,0,164],[127,0,164],[129,0,164],[131,0,163],
        [133,0,163],[135,0,163],[137,0,162],[139,0,162],[141,0,161],[143,0,160],[145,0,160],[147,0,159],[149,0,158],[151,0,157],
        [153,0,156],[155,1,155],[157,1,154],[158,2,153],[160,2,152],[162,3,151],[164,3,150],[165,4,148],[167,4,147],[169,5,146],
        [171,6,144],[172,6,143],[174,7,141],[175,8,140],[177,8,138],[179,9,137],[180,10,135],[182,11,133],[183,12,132],[185,13,130],
        [186,13,128],[188,14,126],[189,15,125],[190,16,123],[192,17,121],[193,18,119],[195,19,117],[196,20,115],[197,22,113],[199,23,111],
        [200,24,109],[201,25,107],[202,26,105],[204,27,103],[205,29,101],[206,30,99],[207,31,97],[208,32,95],[209,34,93],[210,35,90],
        [212,36,88],[213,38,86],[214,39,84],[215,41,82],[216,42,80],[217,44,78],[218,45,75],[219,47,73],[220,48,71],[221,50,69],
        [222,51,67],[223,53,65],[223,54,62],[224,56,60],[225,58,58],[226,59,56],[227,61,54],[228,63,52],[229,64,50],[229,66,47],
        [230,68,45],[231,69,43],[232,71,41],[232,73,39],[233,75,37],[234,76,35],[234,78,33],[235,80,31],[236,82,29],[236,84,27],
        [237,86,26],[238,87,24],[238,89,22],[239,91,20],[240,93,18],[240,95,16],[241,97,15],[241,99,13],[242,101,11],[242,102,10],
        [243,104,8],[243,106,7],[244,108,5],[244,110,4],[245,112,2],[245,114,1],[246,116,0],[246,118,0],[246,120,0],[247,122,0],
        [247,123,0],[248,125,0],[248,127,0],[248,129,0],[249,131,0],[249,133,0],[249,135,0],[250,137,0],[250,139,0],[250,141,0],
        [251,143,0],[251,144,0],[251,146,0],[251,148,0],[252,150,0],[252,152,0],[252,154,0],[252,156,0],[252,157,0],[253,159,0],
        [253,161,0],[253,163,0],[253,165,0],[253,167,0],[254,168,0],[254,170,0],[254,172,0],[254,174,0],[254,175,0],[254,177,0],
        [254,179,0],[254,180,0],[255,182,0],[255,184,0],[255,185,0],[255,187,0],[255,189,0],[255,190,0],[255,192,0],[255,194,0],
        [255,195,0],[255,197,0],[255,198,1],[255,200,3],[255,201,5],[255,203,7],[255,204,9],[255,206,12],[255,207,14],[255,208,16],
        [255,210,19],[255,211,22],[255,213,24],[255,214,27],[255,215,30],[255,217,33],[255,218,36],[255,219,40],[255,221,43],[255,222,47],
        [255,223,50],[255,224,54],[255,225,58],[255,227,62],[255,228,66],[255,229,70],[255,230,75],[254,231,79],[254,232,84],[254,233,88],
        [254,234,93],[254,235,98],[254,236,103],[254,237,108],[254,238,114],[254,239,119],[254,240,125],[254,241,131],[253,242,137],[253,243,143],
        [253,244,149],[253,245,155],[253,246,161],[253,247,168],[253,248,175],[253,249,182],[253,249,189],[253,250,196],[252,251,203],[252,252,210],
        [252,253,218],[252,253,226],[252,254,234],[252,255,242],[252,255,250],[252,255,255]
      ];


      function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

      function toHex(v) { var h = v.toString(16); return h.length === 1 ? "0" +
      h : h; }


      // Build numeric array for scaling

      // Ignore nulls and ignore 0 (and anything <= 0) so it does not skew the
      palette

      var numeric = [];

      for (var a = 0; a < all.length; a++) {
        var vv = all[a];
        if (vv !== null && isFinite(vv) && vv > 0) numeric.push(vv);
      }


      // Fallback: if everything was 0 or null, fall back to any finite values

      if (numeric.length === 0) {
        for (var b = 0; b < all.length; b++) {
          var vv2 = all[b];
          if (vv2 !== null && isFinite(vv2)) numeric.push(vv2);
        }
      }

      if (numeric.length === 0) return [];


      var min = Math.min.apply(null, numeric);

      var max = Math.max.apply(null, numeric);

      var range = (max - min) || 1;


      function valueToColor(v) {
        var t = clamp((v - min) / range, 0, 1);
        // Better mapping than round: ensures max hits 255 reliably
        var idx = clamp(Math.floor(t * 256), 0, 255);
        var rgb = ironbowPalette[idx];
        return "#" + toHex(rgb[0]) + toHex(rgb[1]) + toHex(rgb[2]);
      }


      var start = new Date();

      start.setHours(0, 0, 0, 0);

      var stepMs = 15 * 60 * 1000;


      var result = [];

      for (var k = 0; k < all.length; k++) {
        var x = start.getTime() + k * stepMs;
        var y = all[k];
        if (y === null || !isFinite(y)) {
          result.push({ x: x, y: null });
        } else {
          result.push({ x: x, y: y, fillColor: valueToColor(y) });
        }
      }


      return result;

      
```

<img width="389" height="265" alt="image" src="https://github.com/user-attachments/assets/a4114b64-c6c7-474c-93be-9c394d180d18" />




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
