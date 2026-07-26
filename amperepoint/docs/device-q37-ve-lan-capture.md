# Q37 / EV Charger VE - LAN capture through tuya-local (2026-07-26)

Companion to `device-q37-ve.md`, which describes the same charger as seen
through the Tuya cloud. This file records what the unit reports over the LAN
while paired with `amperepoint_q11_pro_evcharger`, because that profile is
being grown into a single profile for the whole Q Series.

Two of the open questions in the cloud document are answered here, and the
answers go the other way than the cloud observations suggested. Both are
called out below.

- Product/model id: `fdfjiphjxtc9qyhd`
- Profile used while capturing: `amperepoint_q11_pro_evcharger`
- Method: `LOCAL DPS` line logged by tuya-local at the device-type step, plus
  the recorder history of the resulting entities across two charge sessions.

## Datapoints while idle

```json
{"3": "charger_free", "4": 16, "9": 0, "10": 0, "13": "controlpi_12v",
 "14": "charge_now", "18": true, "24": 28}
```

Eight datapoints, the same set, the same types and the same value vocabulary
as the Q11 PRO reported on 2026-07-25 - only the values differ (16 A instead
of 8 A, 28 C instead of 25 C). This is what makes one profile possible: no
datapoint has to be typed differently per generation.

Not reported by this unit, in any state:

| DP | Meaning | Note |
| --- | --- | --- |
| `17` | Target energy | never seen, also absent on the Q11 |
| `25` | Last session energy | never seen, although the cloud exposes `charge_energy_single` |

Both stay `optional: true` in the profile, so their absence cannot hide the
profile from the device-type list.

## Two charge sessions

Recorder history, both sessions single-phase on L1:

| Time | DP1 total energy | Power | L1 | L2 / L3 |
| --- | --- | --- | --- | --- |
| 13:12:46 | `unknown` | 0 kW | 0.0 A | 0.0 A |
| 13:14:48 | 0.00 kWh | - | 229.0 V | - |
| 13:15:00 | - | 1.533 kW | 219.0 V, 7.2 A, 1.533 kW | 0.0 |
| 13:16:18 | 0.03 kWh | - | - | - |
| 13:16:31 | - | 0 kW | 0.0 A | 0.0 |
| 13:17:56 | 0.04 kWh | session 1 ended | - | - |
| 13:19:33 | - | 1.519 kW | 7.3 A | 0.0 |
| 13:20:45 | 0.07 kWh | - | - | - |
| 13:21:25 | - | 0 kW | 0.0 A | 0.0 |
| 13:22:15 | 0.08 kWh | session 2 ended | - | - |

### Correction 1: DP1 does not reset per session

`device-q37-ve.md` records DP1 resetting at a new plug/charge and concludes
"leave unmapped because Q37 DP1 is a resetting session counter". Over the LAN
it did not reset: session 2 continued from 0.04 kWh to 0.08 kWh instead of
restarting near zero. The readings are also consistent as a meter - 90 s at
1.533 kW is 0.038 kWh, and the meter moved 0.04 kWh over session 1.

The profile therefore maps DP1 as a `total_increasing` energy sensor. That
class is the safe choice even if a longer test later finds a daily or monthly
rollover, because Home Assistant treats a drop in a `total_increasing` sensor
as a meter reset and keeps the long-term statistic intact.

Scope of the evidence: two sessions, about four minutes of charging, one
calendar day, one unit. It rules out a per-session reset. It does not rule
out a reset on a longer boundary.

### Correction 2: the phase payloads decode correctly

`device-q37-ve.md` reports implausible phase values and disables DP6/7/8 for
this generation. Decoded with the masks this profile already used for the
Q22 - voltage `FFFF0000000000` scale 10, current `0000FFFFFF0000` scale
1000, power `0000000000FFFF` scale 1000 - the same unit produced physically
consistent readings: 219.0 V x 7.2 A = 1.58 kW against a reported 1.533 kW,
and 229.0 V unloaded sagging to 219.0 V under load.

L2 and L3 stayed at exactly 0.0 throughout. Note what this does and does not
prove: the Q37 is a single-phase unit, so empty L2/L3 is the expected result,
not evidence about the three-phase case from issue 18. It does show the
decoder produces clean zeros rather than noise. The three-phase case has to
be confirmed on a Q11.

The load during both sessions was a kettle on a test rig, not a vehicle,
which is why the parameters repeat so exactly between sessions.

The raw base64 payloads were not retained in the log; the values above come
from the decoded entities in the recorder.

Session energy read 0.08 kWh at the end, covering both bursts rather than
restarting at 13:19. That is intended: the vehicle stayed connected the whole
time (`binary_sensor` on from 13:14:48, DP13 `controlpi_6v` throughout), and
a session is bounded by the plug-in, not by a stop/start of the charge.

### DP9 is watts on this generation too

1533 W reported on DP9 next to L1 at 219.0 V and 7.2 A. The `scale: 1000`
that was corrected for the Q11 is right here as well, so the scale does not
have to vary per generation.

## Charging current range

No conflict between these two generations. Per amperepoint.pl the series
names are kilowatts, not amperes:

| Model | Power | Current | Phases |
| --- | --- | --- | --- |
| Q37 | 3.7 kW | 6-16 A, 1 A steps | 1 |
| Q11 | 11 kW | 6-16 A | 3 |
| Q74 | 7.4 kW | up to 32 A | 1 |
| Q22 | 22 kW | up to 32 A | 3 |

Both captured units are 16 A, so the profile keeps `range: 6..16`.

`models.py` inherited from the base repo read "Q37" as 37 A and declared the
model as 48 A three-phase, the exact opposite of the product. That is
corrected here: Q37 is 1 phase / 16 A, Q11 is 3 phases / 16 A.

Still open for a truly universal profile: the 32 A models (Q22, Q74) do not
fit a 6-16 A range, and the charger publishes no minimum/maximum datapoint to
tell generations apart. Decide that when one of them is actually captured -
not from the model name.

## Matcher result after adding the product id

Replayed against the real tuya-local matcher with the captured datapoints:

| Input | Our profile |
| --- | --- |
| Q11 idle, no product id | `matches=True`, quality 100 |
| Q37 idle, no product id | `matches=True`, quality 100 |
| Q37 idle, product id | `matches=True`, quality 101 |
| Q37 charging, product id | `matches=True`, quality 101 |

101 is the score tuya-local gives a product-id match. `amperepoint_ve_evcharger`
declares the same id and also scores 101, so both appear at the top of the
device-type list; the `(local)` marker in the model name tells them apart.

## Still to capture

- Q22 OTA (`cu111poj2mtikvls`) and the legacy Q Series, to confirm the
  datapoint set holds there too.
- A long enough run to see whether DP1 rolls over on a daily boundary.
- Any unit that actually reports DP17 or DP25 over the LAN.
