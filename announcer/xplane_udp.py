"""
X-Plane 12 UDP Dataref Interface.
Communicates with X-Plane using the native RREF protocol.
Thread-safe, handles automatic subscription, renewal, and packet decoding.
"""

import socket
import struct
import threading
import time
import logging

logger = logging.getLogger("CabinAnnouncer.UDP")

class XPlaneUDP:
    def __init__(self, xplane_ip="127.0.0.1", xplane_port=49000, local_port=0):
        self.xplane_ip = xplane_ip
        self.xplane_port = int(xplane_port)
        self.local_port = int(local_port)
        
        self.sock = None
        self._running = False
        self._thread = None
        self._lock = threading.Lock()
        
        # Dataref registries
        # name -> id
        self._dref_to_id = {}
        # id -> name
        self._id_to_dref = {}
        # name -> float value
        self._values = {}
        # id counter
        self._next_id = 1
        
        # Connection status tracking
        self.last_received_time = 0
        self.connected = False
        self.packets_received = 0
        self._last_retry_time = 0
        self._retry_interval = 2.0  # seconds between RREF resubscription pings when disconnected

    def start(self):
        """Starts the UDP client and background receive thread."""
        if self._running:
            return
            
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # Try preferred local port or bind to any available port
            try:
                self.sock.bind(("", self.local_port))
            except Exception:
                self.sock.bind(("", 0))
            self.sock.settimeout(0.5)
            self._running = True
            
            actual_port = self.sock.getsockname()[1]
            logger.info(f"UDP socket bound to local port {actual_port}, targeting X-Plane at {self.xplane_ip}:{self.xplane_port}")
            
            self._thread = threading.Thread(target=self._receive_loop, daemon=True)
            self._thread.start()
        except Exception as e:
            logger.error(f"Failed to start UDP socket: {e}")

    def stop(self):
        """Stops the UDP receive thread and closes socket."""
        self._running = False
        if self.sock:
            try:
                # Unsubscribe all
                self.unsubscribe_all()
                time.sleep(0.1)
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def subscribe(self, dataref_name, frequency=5):
        """
        Subscribes to a dataref at the given frequency (times per second).
        """
        if not self.sock:
            return None

        dataref_name = dataref_name.strip()
        with self._lock:
            if dataref_name in self._dref_to_id:
                dref_id = self._dref_to_id[dataref_name]
            else:
                dref_id = self._next_id
                self._next_id += 1
                self._dref_to_id[dataref_name] = dref_id
                self._id_to_dref[dref_id] = dataref_name

        self._send_rref(dref_id, frequency, dataref_name)
        return dref_id

    def unsubscribe(self, dataref_name):
        """Unsubscribes from a dataref (frequency = 0)."""
        with self._lock:
            dref_id = self._dref_to_id.get(dataref_name)
        if dref_id is not None:
            self._send_rref(dref_id, 0, dataref_name)

    def unsubscribe_all(self):
        """Unsubscribes from all currently registered datarefs."""
        with self._lock:
            items = list(self._dref_to_id.items())
        for name, dref_id in items:
            self._send_rref(dref_id, 0, name)

    def resubscribe_all(self, frequency=5):
        """Resends subscription requests for all registered datarefs."""
        with self._lock:
            items = list(self._dref_to_id.items())
        for name, dref_id in items:
            self._send_rref(dref_id, frequency, name)

    def _send_rref(self, dref_id, frequency, dataref_name):
        """Packs and sends a single RREF dataref request packet."""
        if not self.sock:
            return
        try:
            cmd = b"RREF\x00"
            dref_encoded = dataref_name.encode("utf-8")[:400]
            dref_padded = dref_encoded.ljust(400, b"\x00")
            msg = struct.pack("<5sii400s", cmd, int(frequency), int(dref_id), dref_padded)
            self.sock.sendto(msg, (self.xplane_ip, self.xplane_port))
        except Exception as e:
            logger.debug(f"Failed to send RREF for {dataref_name}: {e}")

    def send_command(self, command_name):
        """Sends an X-Plane command packet (CMND)."""
        if not self.sock or not command_name:
            return
        try:
            cmd_hdr = b"CMND\x00"
            cmd_encoded = command_name.strip().encode("utf-8")
            msg = cmd_hdr + cmd_encoded + b"\x00"
            self.sock.sendto(msg, (self.xplane_ip, self.xplane_port))
            logger.info(f"Sent X-Plane command: {command_name}")
        except Exception as e:
            logger.debug(f"Failed to send command '{command_name}': {e}")

    def get_value(self, dataref_name, default=0.0):
        """Gets the most recently received value for a dataref."""
        with self._lock:
            return self._values.get(dataref_name, default)

    def get_all_values(self):
        """Returns a snapshot copy of all received dataref values."""
        with self._lock:
            return dict(self._values)

    def is_connected(self):
        """Returns True if dataref packets were received in the last 3 seconds."""
        return (time.time() - self.last_received_time) < 3.0

    def _receive_loop(self):
        """Background thread receiving and parsing UDP packets from X-Plane."""
        while self._running:
            try:
                data, addr = self.sock.recvfrom(4096)
                if not data:
                    continue

                self.last_received_time = time.time()
                self.connected = True
                self.packets_received += 1

                # Parse RREF response packets
                if len(data) >= 5 and data.startswith(b"RREF"):
                    payload = data[5:]
                    entry_size = 8
                    num_entries = len(payload) // entry_size

                    with self._lock:
                        for i in range(num_entries):
                            chunk = payload[i * entry_size : (i + 1) * entry_size]
                            if len(chunk) == 8:
                                dref_id, value = struct.unpack("<if", chunk)
                                dref_name = self._id_to_dref.get(dref_id)
                                if dref_name:
                                    self._values[dref_name] = value

            except socket.timeout:
                now = time.time()
                if self.connected and (now - self.last_received_time) >= 3.0:
                    self.connected = False
                    logger.info("Lost connection to X-Plane (timeout). Entering auto-reconnect mode...")

                # Auto-retry connection ping when disconnected
                if not self.connected and (now - self._last_retry_time) >= self._retry_interval:
                    self._last_retry_time = now
                    self.resubscribe_all()
            except Exception as e:
                if self._running:
                    logger.debug(f"UDP receive error: {e}")
                    time.sleep(0.05)
