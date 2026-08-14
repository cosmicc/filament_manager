- ~~**Print history tied to exact material state**~~
Finished Print info can be obtained from moonraker/klipper
Create a canonical PrintJob record containing things like:
printer
spool
material profile version
build plate
nozzle
Cura profile version
G-code hash
predicted filament usage
actual filament usage
start/end time
duration
completion/cancel/failure
layer height
print speed
temperatures
pressure advance
retraction
flow
slicer version
Moonraker job ID
Timelapse video link


- ~~**Print outcome / quality scoring**~~
After a print finishes, offer a very small assessment (and/or pull from moonraker/klipper completed prints):
Successful
Failed
Acceptable
Excellent

Then optional defect tags:
stringing
blobs/zits
underextrusion
overextrusion
poor bridging
poor overhangs
warping
elephant foot
weak layer adhesion
poor top surface
dimensional error
supports difficult to remove
supports fused
seam artifacts


- **Calibration results as actual measurements**
current calibration workflow already covers temperature, flow, pressure advance, retraction, overhang, and ironing.
I would make every calibration test produce structured results instead of just a final selected number.
For example:
Retraction calibration
2.0 mm   heavy stringing
2.5 mm   moderate stringing
3.0 mm   slight stringing
3.5 mm   clean
4.0 mm   clean
4.5 mm   surface defects
5.0 mm   surface defects

Selected:
3.7 mm

Then keep the full calibration evidence forever.

You could graph:
PA versus corner quality
flow versus dimensional accuracy
temperature versus stringing
temperature versus bridging
retraction versus stringing
speed versus print-quality score


- **Make profiles hierarchical**
At the moment profiles are scoped by printer and nozzle diameter. I would extend this to inheritance.
For example:
Material Family
    PLA
      ↓
Manufacturer Material
    Polymaker PolyLite PLA
      ↓
Color
    Black
      ↓
Printer
    FLSun QQ-S
      ↓
Nozzle
    0.6 mm
      ↓
Profile

Settings inherit downward unless overridden.

So you might have:
PLA defaults
    temperature = 200
    fan = 100%
Polymaker PolyLite PLA
    temperature = 205
Black
    flow = 92%
FLSun QQ-S
    pressure_advance = 0.14
0.6 mm nozzle
    retraction = 4.2

The effective profile is composed automatically.


- **Filament environmental tracking**
This could be a major differentiator.
Add:
drying_status
last_dried_at
drying_temperature
drying_duration
dryer_id
humidity_before
humidity_after

Then eventually connect an ESP32 humidity sensor.

You could have:
Spool A
PETG
Last dried: 12 days ago
Dry box RH: 37%
Recommendation: Dry before printing

Or automatically generate alerts.
The system could eventually correlate humidity with print defects.

Dry-box management

Since you're already considering scales and NFC, I would define DryBox as a first-class object.

Something like:
DryBox
 ├── NFC reader
 ├── load cell
 ├── humidity sensor
 ├── temperature sensor
 ├── heater
 └── spool

Then expose:
Loaded spool
Current measured mass
Remaining filament
Humidity
Temperature
Drying state
Printer assignment

The future workflow becomes very clean:

Insert spool
       ↓
NFC detected
       ↓
Filament Manager identifies spool
       ↓
Scale validates weight
       ↓
Spool automatically becomes active
       ↓
Moonraker / Spoolman updated

The architecture already anticipates authenticated device adapters and NFC mappings. I would formalize the device model sooner rather than later.



- **Create a device API**
Instead of writing special server integrations for every sensor, expose a generic API:
/api/devices
/api/devices/{id}/telemetry
/api/devices/{id}/events

Devices could include:
scale
NFC reader
dry box
humidity sensor
barcode scanner
printer
filament dryer
camera
temperature probe


- **Filament consumption prediction**
Once you have print history, you can compare:
Cura estimated consumption
Spoolman measured consumption
Scale measured consumption

and calculate correction factors.

For example:
Cura estimate:      182.4 g
Spoolman estimate:  177.8 g
Scale difference:   175.9 g

Prediction error: +3.7%

Then Filament Manager can learn:
Corrected expected usage:
175.7 g

This becomes extremely useful for expensive or nearly-empty spools.

Better “can I print this?” checks
You already intend to warn when a spool is insufficient or materially incompatible.
I'd expand that into a preflight engine.
When a job enters Moonraker:
MODEL: enclosure_bracket.gcode

Required filament:   328 g
Available filament:  412 g

Material: PETG ✓
Nozzle: 0.6 mm ✓
Build plate: P3 ✓
Profile: PETG v9 ✓
Bed mesh: P3 ✓
Filament dry: ⚠

Result:
READY WITH WARNING
Filament was last dried 21 days ago.
Or:
BLOCKED

Only 241 g available.
Print requires approximately 328 g.

You might not actually stop prints by default, but provide configurable policies.


- ~~**G-code inspection**~~

When Moonraker receives a file, Filament Manager could inspect the G-code header.
Cura embeds a lot of useful metadata.
Extract:
Cura version
material
estimated weight
estimated length
layer height
line width
nozzle diameter
temperatures
print time
support configuration
machine

Then compare that against the active Filament Manager profile.

Example:
G-code requests nozzle temp 240°C
Current SPLA profile specifies 225°C

⚠ Profile mismatch

That is a very useful safety net.


- **Profile drift detection**
Because your Cura workstation agent deploys actual Cura files and tracks checksums, you have an opportunity to detect local edits.
For example:
Cura workstation: GARUDA-LAPTOP

Expected:
PETG FLSun 0.6 v12

Detected:
Modified locally

Differences:
retraction_distance
4.2 → 4.8

flow
93 → 95

Then let the user:
Restore canonical profile
Import changes as new profile version
Ignore

That would make your profile deployment system unusually robust.


- **Profile branching**
may eventually want profiles like:

PETG / Quality
PETG / Fast
PETG / Strong
PETG / Dimensional
PETG / Vase

Instead of forcing one “best PETG profile.”

So support:
base profile
 ├── Quality
 ├── Speed
 ├── Strength
 └── Prototype

Each only overrides a few parameters.


- ~~**Dimensional calibration**~~
Given that you're already doing dimensional tuning on the printer, I would absolutely add this to the calibration system.

Track:
design X
measured X
design Y
measured Y
design Z
measured Z
hole design
hole measured
shaft design
shaft measured

Then derive recommended:
horizontal expansion
hole horizontal expansion
flow
printer dimensional correction

Importantly, Filament Manager could distinguish:
printer geometry correction
from
material shrinkage correction

Those shouldn't be treated as the same thing.


- **Material property database**
Extend materials beyond slicer settings.
Store things like:
density
glass transition temperature
heat deflection temperature
recommended nozzle
abrasive
hygroscopicity
UV resistance
chemical resistance
flexibility
strength
food contact notes
drying temperature
drying duration
maximum drying temperature

Then Filament Manager can become useful when choosing a material, not just configuring one.

For example:
Show me materials I own that are suitable for outdoor use and can handle 70°C.


- **Nozzle tracking**
I'd strongly recommend turning nozzles into inventory objects.

Something like:
Nozzle N3
Printer: FLSun
Diameter: 0.6 mm
Material: hardened steel
Installed: 2026-07-21
Filament printed: 4.83 kg
Abrasive filament: 1.71 kg

Then alert based on usage.

That becomes especially valuable when you start using carbon/glass/wood-filled materials.

You could track:
wear_index
weighted based on material abrasiveness.


- **Printer component lifecycle**
You could generalize that concept to:
nozzle
Bowden tube
extruder gear
bed surface
belts
fans
heater cartridge
thermistor

and associate maintenance schedules with runtime or filament consumed.

Example:
Bowden tube
Installed: 2026-03-10
Filament passed: 18.7 kg

This turns the application slightly toward printer fleet management without losing the filament focus.


- **Build plate lifecycle**
build plates currently track condition, cleaning, mesh calibration and material suitability.

I'd expand that into:
print count
hours used
last washed
last IPA clean
adhesive used
surface damage
mesh variance

Then correlate:
bed adhesion failures by plate

You may discover:
72% of PETG adhesion failures occur on P2.


- **Automatic build-plate recommendation**
At print preparation, recommend a physical build plate and side using material compatibility,
surface properties, temperature limits, condition, maintenance state, mesh freshness, and
recorded print outcomes. Keep the recommendation advisory and defer it until the application
has enough compatibility and print-history data to make a useful choice.


- **Print failure analytics**
Once you combine print jobs + outcome tags:

Failure rate by:
printer
material
manufacturer
color
profile
nozzle
plate
temperature
humidity
operator

You get genuinely useful analytics.

For example:
PETG failure rate
P1       3%
P2      17%
P3       4%

Or:
Retraction >5 mm correlates with increased nozzle clogs.


- **Automatic profile recommendations**
Eventually, Filament Manager could calculate a candidate profile from history.

Not “AI” in the marketing sense. Simple statistics first.
For example:

Successful prints using eSUN PETG:
17
Median nozzle temp:
236°C
Median flow:
92.5%
Median PA:
0.082

Recommended candidate:
237°C / 93% / PA 0.08

Then the user explicitly approves:
Create profile v14

No silent changes.


- ~~**Compare profiles visually**~~
Build a side-by-side diff:

Parameter	v10	v11	v12
Temp	235	240	238
Flow	95%	93%	92%
PA	.09	.08	.08
Retract	4.5	4.2	4.0

And below it:
Success Rate
v10  82%
v11  91%
v12  96%

This would fit naturally with the immutable profile-version architecture you already have.


- **QR label improvements**
Labels could contain more than just spool ID.
I'd support configurable templates:

[ QR ]

SP-0142
Polymaker PETG
Black
1.75 mm

Net: 734 g

And possibly a QR URL:
https://filament.example/spool/SP-0142

Scan from a phone and immediately open:
spool
weight
profile
usage
drying
prints


- **Mobile-first scanner mode**
Create a stripped-down /scan interface.
The workflow:
Scan QR
↓
Huge spool card
↓
[ LOAD ]
[ WEIGH ]
[ DRY ]
[ VIEW ]

This would be ideal next to the printer.

A USB scanner could also send IDs directly into this interface.


- **Material purchasing and cost analytics**
You're already storing costs.
Expand this to:
price/kg
shipping
vendor
order date
delivery date
lot
sale price

Then calculate:
cost per print
cost per successful print
filament waste cost
cost by material
monthly filament usage

Example:
Gearbox housing
Filament used: 187 g
Material cost: $4.21
Failed attempts: $2.87
Total material cost: $7.08


- **Reorder management**
Once spool inventory is accurate:

Polymaker PETG Black
Total available: 734 g
Minimum target: 1,500 g

⚠ REORDER

Eventually:
Average usage: 380 g/month
Estimated remaining supply: 1.9 months


- **API-first architecture**
make basically everything the UI does available through a stable API:

/api/v1/spools
/api/v1/materials
/api/v1/profiles
/api/v1/printers
/api/v1/prints
/api/v1/calibrations
/api/v1/devices

Then external projects become much easier.

I'd also generate an SDK from FastAPI's OpenAPI spec.

Python first:
fm.spools.get("SP-0142")
fm.printers.set_active_spool(...)


- **Webhooks**
Add outgoing webhooks:
spool.low
spool.loaded
spool.empty
print.started
print.completed
print.failed
calibration.completed
profile.published
device.offline

Then Home Assistant, Node-RED, Discord, MQTT bridges, etc. become trivial.


- **Backup/restore validation**
Since PostgreSQL is deliberately canonical and projections are rebuildable, add an application-level command like:

filament-manager verify

that checks:
database migrations
Spoolman consistency
orphan projections
Google Sheet projection
missing profile deployments
device credentials
measurement integrity

Then:
filament-manager rebuild-projections


- **Observability**
You already expose Prometheus metrics.
Expand them with domain metrics:

filament_spools_total
filament_mass_grams
filament_usage_grams_total
print_jobs_total
print_failures_total
projection_queue_depth
projection_failures_total
spoolman_reconcile_seconds
cura_agents_online
device_last_seen_seconds
drybox_humidity

Then your Grafana stack can monitor the printing environment too.


- **The architecture I think this should evolve toward**
Something like:

                        ┌───────────────────┐
                        │   Filament Manager│
                        │     FastAPI       │
                        └────────┬──────────┘
                                 │
                         PostgreSQL
                         Canonical DB
                                 │
          ┌──────────────────────┼─────────────────────┐
          │                      │                     │
        Outbox               Print Jobs          Device Events
          │
   ┌──────┼─────────┐
   │      │         │
Spoolman Cura    Google Sheets
   │      │
Moonraker Agents
   │
Klipper

ESP32 / Devices
   │
   ├── Scale
   ├── NFC
   ├── Humidity
   └── Dryer

And above all of that:

Calibration
      ↓
Profiles
      ↓
Prints
      ↓
Results
      ↓
Recommendations
      ↓
New Profile Version

That last feedback loop is where I think the application becomes genuinely distinctive.

The five things I would build next

If this were my roadmap, I would prioritize:

Canonical PrintJob + print history
Print result/defect tracking
Multi-printer data-driven Moonraker integration
Generic Device API + MQTT for scale/NFC/dry box
Profile inheritance + profile comparison/analytics

After those, add G-code preflight, material environmental tracking, nozzle/component lifecycle, and statistical profile recommendations.

GUI audit follow-ups

- ~~**Account lifecycle controls**~~
  Add secure Administrator workflows to edit roles and display names, deactivate or reactivate accounts, and reset passwords without recreating users.

- ~~**Build-plate maintenance history**~~
  Add explicit Mark Cleaned and Mark Mesh Calibrated actions, immutable maintenance records, due-state reminders, and filterable plate history.

- ~~**Active-context controls**~~
  Add an intentional in-app Clear Active Spool action, identify the assigned printer by name, and provide the same explicit clear behavior for the selected build-plate side.

- ~~**Mobile data views**~~
  Replace horizontally scrolling inventory, profile, activity, integration-job, label, and deployment tables with compact mobile cards that keep their primary actions visible.

- ~~**Operator notifications**~~
  Add an in-app notification center for unavailable Moonraker connections, dead projection jobs, low or empty spools, overdue plate maintenance, and Cura deployment failures while retaining structured service logs.
