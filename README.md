# Satellite HIL/SIL Simulator — Plant MVP

This repository contains the initial Plant (Python) MVP for a modular Satellite HIL/SIL simulator.

## Setup
1. Create a Python 3.10+ environment.
2. Install dependencies:
```
pip install -r requirements.txt
```

## Run Plant
```
python -m plant.plant --config plant/config_default.yaml
```

The Plant emits NDJSON sensor frames (GPS @ 1 Hz, Gyro @ 100 Hz) to UDP `127.0.0.1:10001`, listens for actuator frames on `:10002`, and logs all frames to `logs/replay.ndjson`.

## Tests
Run unit tests:
```
pytest -q
```

## Sample NDJSON
```
{"type":"sensor","protocol_version":"1.0","schema_version":"gps-v1","sensor":"gps","t_sim":0.0,"t_sent":null,"seq":1,"payload":{"r_eci":[6871001.2,0.3,-1.0],"v_eci":[-0.2,7609.6,0.1]}}
{"type":"sensor","protocol_version":"1.0","schema_version":"gyro-v1","sensor":"gyro","t_sim":0.0,"t_sent":null,"seq":1,"payload":{"omega_body":[0.0001,0.0,0.0]}}
```

See `docs/CONVENTIONS.md` for quaternion and unit conventions.


