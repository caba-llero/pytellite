from __future__ import annotations

import json
import socket
from typing import Optional

from jsonschema import Draft202012Validator


# Not currently used! Perhaps in the future we will use for 
# software-in-the-loop simulation (the initial idea of the project)

def load_protocol_schemas(schema_path: str) -> dict:
    with open(schema_path, "r", encoding="utf-8") as f:
        return json.load(f)


class NDJSONUDPSocket:
    """
    NDJSONUDPSocket is a class that handles the sending and receiving of NDJSON over UDP.
    It is used to send and receive messages between the plant and the flight software.
    """
    def __init__(self, send_host: str, send_port: int, recv_port: int, recv_timeout: float = 0.0):
        self.sock_send = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.send_addr = (send_host, send_port)

        self.sock_recv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock_recv.bind(("0.0.0.0", recv_port))
        # Non-blocking by default to avoid stalling the simulation loop
        self.sock_recv.settimeout(max(0.0, recv_timeout))

    def send_json(self, obj: dict): # send a json object to the flight software
        line = json.dumps(obj, separators=(",", ":")) + "\n"
        self.sock_send.sendto(line.encode("utf-8"), self.send_addr)

    def try_recv_json(self) -> Optional[dict]: # try to receive a json object from the flight software; Optional as it may not receive anything
        try:
            data, _ = self.sock_recv.recvfrom(65535) # 65535 is the max UDP packet size
        except socket.timeout: 
            return None
        except BlockingIOError:
            return None
        line = data.decode("utf-8").strip()
        if not line:
            return None
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return None


class SchemaRegistry:
    def __init__(self, schemas: dict):
        self.schemas = schemas
        self.validators = {
            "gyro-v1": Draft202012Validator(self.schemas["sensor-gyro-v1"]),
            "gps-v1": Draft202012Validator(self.schemas["sensor-gps-v1"]),
        }

    def validate_sensor(self, msg: dict) -> None:
        schema_version = msg.get("schema_version", "")
        if schema_version not in self.validators:
            raise ValueError(f"Unknown sensor schema: {schema_version}")
        self.validators[schema_version].validate(msg)


