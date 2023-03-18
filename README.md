# oem2mqtt

Parse raw UDP messages in OEM format and publish values to MQTT broker.

## Environament variables

See commonn environment variables from [MQTT-Framework](https://github.com/paulianttila/MQTT-Framework).

| **Variable**                 | **Default** | **Descrition**                                                                                                |
|------------------------------|-------------|---------------------------------------------------------------------------------------------------------------|
| CFG_APP_NAME                 | oem2mqtt    | Name of the app.                                                                                              |
| CFG_UDP_PORT                 | 9999        | UDP port to listen.                                                                                           |
| CFG_MSG_THROTTLE_TIME        | 5           | Message throttle time in seconds. Can be used to limit incoming message parsing.                              |
| CFG_CACHE_TIME               | 300         | Cache time in seconds for OEM values. During cache time, values are only updeted to MQTT if value changed.    |
| CFG_INCLUDE_NODE_ID_TO_TOPIC | True        | Add node id to MQTT topic. Usefull when have more than one node                                               |

## Message parsers

Create .env_msg_parsers file

```bash
nano .env_msg_parsers
```

add following environment variables for message parsing

```properties
CFG_MSG_PARSER_RULE_NODE_X=
CFG_MSG_PARSER_VAR_NAMES_NODE_X
CFG_MSG_PARSER_VAR_SCALERS_NODE_X

CFG_MSG_PARSER_RULE_NODE_Y=
CFG_MSG_PARSER_VAR_NAMES_NODE_Y
CFG_MSG_PARSER_VAR_SCALERS_NODE_Y
```

Where parser rule support following values

```
b: byte, 1 byte
h: short integer, 2 bytes
i: integer, 4 bytes
l: long, 4 bytes
q: long long, 8 bytes
f: float, 4 bytes
d: double, 8 bytes
B: unsigned byte, 1 byte
H: unsigned short integer, 2 bytes
I: unsigned integer, 4 bytes
L: unsigned long, 4 bytes
Q: unsigned long long, 8 bytes
c: char, 1 byte
```

## Example

Parsers for node 10
```properties
CFG_MSG_PARSER_RULE_NODE_10=H, H, H, H, H, H, H, H, H, H, H, H, H, H, H, L, H, H, H, H, H
CFG_MSG_PARSER_VAR_NAMES_NODE_10=phase1RealPower, phase1ApparentPower, phase1Current, phase1PowerFactor, phase2RealPower, phase2ApparentPower, phase2Current, phase2PowerFactor, phase3RealPower, phase3ApparentPower, phase3Current, phase3PowerFactor, realPower, apparentPower, voltage, pulseCount, pulsePower, temperature1, temperature2, temperature3, temperature4
CFG_MSG_PARSER_VAR_SCALERS_NODE_10=1, 1, 0.01, 0.01, 1, 1, 0.01, 0.01, 1, 1, 0.01, 0.01, 1, 1, 1, 1, 1, 0.01, 0.01, 0.01, 0.01
```

### Example data

Simulate real data by sending raw UDP message from commandline

```bash
echo "10 79 1 82 2 253 0 56 0 109 0 135 0 57 0 80 0 26 0 42 0 18 0 62 0 216 1 4 3 234 0 1 59 128 0 33 0 52 8 0 0 0 0 0 0" | nc -4u -w1 localhost 9999
```

```log
[2023-02-19 11:07:52,480] DEBUG in app: Received data: 10 79 1 82 2 253 0 56 0 109 0 135 0 57 0 80 0 26 0 42 0 18 0 62 0 216 1 4 3 234 0 1 59 128 0 33 0 52 8 0 0 0 0 0 0
[2023-02-19 11:07:52,483] INFO in app: phase1RealPower = 335
[2023-02-19 11:07:52,487] INFO in app: phase1ApparentPower = 594
[2023-02-19 11:07:52,501] INFO in app: phase1Current = 2.53
[2023-02-19 11:07:52,502] INFO in app: phase1PowerFactor = 0.56
[2023-02-19 11:07:52,502] INFO in app: phase2RealPower = 109
[2023-02-19 11:07:52,503] INFO in app: phase2ApparentPower = 135
[2023-02-19 11:07:52,503] INFO in app: phase2Current = 0.57
[2023-02-19 11:07:52,503] INFO in app: phase2PowerFactor = 0.8
[2023-02-19 11:07:52,504] INFO in app: phase3RealPower = 26
[2023-02-19 11:07:52,504] INFO in app: phase3ApparentPower = 42
[2023-02-19 11:07:52,505] INFO in app: phase3Current = 0.18
[2023-02-19 11:07:52,506] INFO in app: phase3PowerFactor = 0.62
[2023-02-19 11:07:52,506] INFO in app: realPower = 472
[2023-02-19 11:07:52,507] INFO in app: apparentPower = 772
[2023-02-19 11:07:52,507] INFO in app: voltage = 234
[2023-02-19 11:07:52,507] INFO in app: pulseCount = 8403713
[2023-02-19 11:07:52,508] INFO in app: pulsePower = 33
[2023-02-19 11:07:52,508] INFO in app: temperature1 = 21
[2023-02-19 11:07:52,509] INFO in app: temperature2 = 0
[2023-02-19 11:07:52,509] INFO in app: temperature3 = 0
[2023-02-19 11:07:52,509] INFO in app: temperature4 = 0
 ```

## Example docker-compose.yaml

```yaml
version: "3.5"

services:
  oem2mqtt:
    container_name: oem2mqtt
    image: paulianttila/oem2mqtt:2.0.0
    restart: unless-stopped
    environment:
      - CFG_LOG_LEVEL=DEBUG
      - CFG_MQTT_BROKER_URL=127.0.0.1
      - CFG_MQTT_BROKER_PORT=1883
      - CFG_INCLUDE_NODE_ID_TO_TOPIC=False
      - CFG_CACHE_TIME=300
      - CFG_MSG_THROTTLE_TIME=1
    env_file:
      - .env_msg_parsers
    ports:
      - "9999:9999/udp"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/healthy"]
      interval: 60s
      timeout: 3s
      start_period: 5s
      retries: 3
 ```