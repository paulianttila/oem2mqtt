from mqtt_framework import Framework
from mqtt_framework import Config
from mqtt_framework.callbacks import Callbacks
from mqtt_framework.app import TriggerSource

from prometheus_client import Counter

import threading
import socket
import struct
import binascii
from cacheout import Cache
from typing import Any

class MyConfig(Config):
    def __init__(self):
        super().__init__(self.APP_NAME)

    APP_NAME = "oem2mqtt"

    # App specific variables

    UDP_PORT = 9999
    CACHE_TIME = 300
    MSG_THROTTLE_TIME = 5
    INCLUDE_NODE_ID_TO_TOPIC = True


class MyApp:
    def init(self, callbacks: Callbacks) -> None:
        self.logger = callbacks.get_logger()
        self.config = callbacks.get_config()
        self.metrics_registry = callbacks.get_metrics_registry()
        self.add_url_rule = callbacks.add_url_rule
        self.publish_value_to_mqtt_topic = callbacks.publish_value_to_mqtt_topic
        self.subscribe_to_mqtt_topic = callbacks.subscribe_to_mqtt_topic
        self.received_messages_metric = Counter(
            "received_messages", "", registry=self.metrics_registry
        )
        self.received_messages_errors_metric = Counter(
            "received_messages_errors", "", registry=self.metrics_registry
        )
        self.exit = False
        self.udp_receiver = None
        self.messageCache = Cache(maxsize=256, ttl=self.config["MSG_THROTTLE_TIME"])
        self.valueCache = Cache(maxsize=256, ttl=self.config["CACHE_TIME"])
        self.parserRuleCache = {}
        self.parserVarNamesCache = {}
        self.parserVarScalersCache = {}
        self.include_node_id_to_topic = False
        if self.config["INCLUDE_NODE_ID_TO_TOPIC"].lower() == "true":
            self.include_node_id_to_topic = True

    def get_version(self) -> str:
        return "1.0.0"

    def stop(self) -> None:
        self.logger.debug("Stopping...")
        self.exit = True
        if self.udp_receiver:
            self.udp_receiver.stop()
            if self.udp_receiver.is_alive():
                self.udp_receiver.join()
        self.logger.debug("Exit")

    def subscribe_to_mqtt_topics(self) -> None:
        pass

    def mqtt_message_received(self, topic: str, message: str) -> None:
        pass

    def do_healthy_check(self) -> bool:
        return self.udp_receiver.is_alive()

    # Do work
    def do_update(self, trigger_source: TriggerSource) -> None:
        self.logger.debug("update called, trigger_source=%s", trigger_source)
        if trigger_source == trigger_source.MANUAL:
            self.valueCache.clear()

        if self.udp_receiver is None:
            self.logger.info("Start UDP receiver")
            self.udp_receiver = threading.Thread(
                target=self.start_udp_receiver, daemon=True
            )
            self.udp_receiver.start()

    def start_udp_receiver(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("0.0.0.0", self.config["UDP_PORT"]))
        self.logger.debug("Waiting data from UDP port %d", self.config["UDP_PORT"])

        while not self.exit:
            try:
                data, addr = sock.recvfrom(1024)  # buffer size is 1024 bytes
                self.received_messages_metric.inc()

                if not data:
                    self.logger.debug("No data")
                    continue
                self.handle_data(data)
            except Exception as e:
                self.received_messages_errors_metric.inc()
                self.logger.error(f"Error occured: {e}")
                self.logger.debug(f"Error occured: {e}", exc_info=True)

        self.logger.debug("UDP receiver stopped")

    def handle_data(self, data: bytes) -> None:
        data = data.decode("ascii")
        # self.logger.debug('Received data (type=%s): %s', type(data), data)

        data = self.remove_line_breaks(data)
        self.logger.debug("Received data: %s", data)

        # Split string into values
        data = data.split(" ")

        nodeid = int(data[0])
        previousMsg = self.messageCache.get(nodeid, None)

        if previousMsg is not None:
            self.logger.debug("Skip message parsing for node id: %s", nodeid)
            return

        values = self.parse_values(nodeid, data)
        names = self.get_parser_variable_names(nodeid)
        scalers = self.get_parser_variable_scalers(nodeid)
        if not len(values) == len(names) == len(scalers):
           self.logger.debug(
                "Array lenghts does not match: len(values)=%d"
                ", len(names)=%d, len(scalers)=%d",
                len(values),
                len(names),
                len(scalers),
            )
           return

        # self.logger.debug('result={0}'.format(values))
        # self.logger.debug('Names: %s' % names)
        # self.logger.debug('Scalers: %s' % scalers)

        for i, val in enumerate(values):
            self.logger.debug(
                "%s : %s (%s:%s)",
                names[i],
                self.scale_value(val, scalers[i]),
                val,
                scalers[i],
            )
            if names[i] != "":
                self.publish_value(
                    nodeid, names[i], self.scale_value(val, scalers[i])
                )
            else:
                self.logger.debug(
                    "Skip message publishing as name is empty: %s", names[i]
                )

        self.messageCache.set(nodeid, data)
 
    def remove_line_breaks(self, data: bytes) -> bytes:
        # Remove CR,LF
        if data.endswith("\n") or data.endswith("\r"):
            data = data[:-1]
        if data.endswith("\n") or data.endswith("\r"):
            data = data[:-1]
        return data

    def parse_values(self, nodeid: int, data: bytes) -> tuple[Any, ...]:
        data = data[1:]
        vals = [int(i) for i in data]
        vals = bytearray(vals)

        unpackStr = self.get_parser_rule(nodeid)
        if unpackStr is None:
            self.logger.debug(
                "Skip message parsing, unpack string not defined for nodeid: %s",
                nodeid,
            )
            return ()

        self.logger.debug(
            "unpackStr=%s, msg len=%s, msg type=%s, data=%s",
            unpackStr,
            len(vals),
            type(vals),
            binascii.hexlify(vals).upper(),
        )

        return struct.unpack(unpackStr, vals)

    def scale_value(self, value, scale: float) -> int | float:
        if scale == 1:
            return value
        val = value * scale
        return int(val) if val % 1 == 0 else round(float(val), 2)

    def publish_value(self, nodeid: int, key: str, value: str) -> None:
        prevVal = self.valueCache.get(key)
        publish = False
        if prevVal is None:
            self.logger.debug("%s: no cache value available", key)
            publish = True
        elif value == prevVal:
            self.logger.debug("%s = %s : skip update because of same value", key, value)
        else:
            publish = True

        if publish:
            self.logger.info("%s = %s", key, value)
            if self.include_node_id_to_topic:
                topic = "node{0}/{1}".format(nodeid, key)
            else:
                topic = key
            self.publish_value_to_mqtt_topic(topic, value, False)
            self.valueCache.set(key, value)

    def get_parser_rule(self, nodeid: int) -> None | str:
        unpack = self.parserRuleCache.get(nodeid)
        if unpack is not None:
            self.logger.debug("unpackStr from cache=%s", unpack)
            return unpack
        else:
            unpack = self.config[f"MSG_PARSER_RULE_NODE_{nodeid}"]
            return None if unpack is None else self.parse_unpack_str(unpack, nodeid)

    def parse_unpack_str(self, unpackStr: str, nodeid: int) -> str:
        unpackStr = unpackStr.replace(" ", "")
        unpackStr = unpackStr.replace(",", "")
        unpackStr = f"<{unpackStr}"
        self.logger.debug("Generated unpackStr=%s", unpackStr)
        self.parserRuleCache[nodeid] = unpackStr
        return unpackStr

    def get_parser_variable_names(self, nodeid: int) -> None | list[str]:
        names = self.parserVarNamesCache.get(nodeid)
        if names is not None:
            self.logger.debug("names from cache=%s", names)
        else:
            names = self.config[f"MSG_PARSER_VAR_NAMES_NODE_{nodeid}"]
            if names is None:
                return None
            names = names.replace(" ", "")
            names = names.split(",")
            self.logger.debug("Generated names=%s", names)
            self.parserVarNamesCache[nodeid] = names
        return names

    def get_parser_variable_scalers(self, nodeid: int) -> None | list[float]:
        scalers = self.parserVarScalersCache.get(nodeid)
        if scalers is not None:
            self.logger.debug("Scalers from cache=%s", scalers)
        else:
            scalers = self.config[f"MSG_PARSER_VAR_SCALERS_NODE_{nodeid}"]
            if scalers is None:
                return None
            s = scalers.replace(" ", "").split(",")
            scalers = [float(i) for i in s]
            self.logger.debug("Generated scalers=%s", scalers)
            self.parserVarScalersCache[nodeid] = scalers
        return scalers

if __name__ == "__main__":
    Framework().start(MyApp(), MyConfig(), blocked=True)
