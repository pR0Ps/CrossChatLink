
import threading
import logging
import queue

import miniboa

#Client connected via telnet
_admin_client = None

#connect and disconnect handlers
def on_connect(client):
    global _admin_client
    logging.info("Client connected from {}".format(client.addrport()))
    _admin_client = client
    _admin_client.send("Welcome to the CrossChatLink admin interface!"
                         "\n\nType 'help' or '?' for a list of commands\n\n")
def on_disconnect(client):
    global _admin_client
    logging.info ("Client disconnected")
    _admin_client = None

class Admin (threading.Thread):
    """
    Provides an admin interface via a telnet server
    """

    def __init__(self, program):
        super(Admin, self).__init__()
        self._program = program
        self._server = miniboa.TelnetServer(23, "127.0.0.1", on_connect,
                                                 on_disconnect, 1, 0.3)
        self._stop_req = threading.Event()
        self.msg_queue = queue.Queue()
        
    def _process_commands(self):
        """Recieves a line from the client and proccesses it (assumes valid client)"""
        if _admin_client.active and _admin_client.cmd_ready:
            msg = _admin_client.get_command()
            #add command to the queue (None for link/user = admin interface)
            self._program.parse_command(msg, None, None, self._program.ADMIN)

    def disconnect_client(self):
        """Sends all messages and disconnects the client"""
        logging.debug("Disconnecting client")
        if _admin_client != None:
            while self._process_queue():
                pass

            #update the client so they get the messages
            self._server.poll()
            _admin_client.deactivate()
            #update so the client is disconnected
            self._server.poll()
        
    def _process_queue(self):
        """Sends messages in the queue to the client (assumes valid client)"""
        if self.msg_queue.qsize() == 0:
            return False
        try:
            _admin_client.send(self.msg_queue.get_nowait() + "\n")
            return True
        except queue.Empty as e:
            pass
        return False

    def run(self):
        """Starts the telnet server"""
        logging.info ("Starting telnet server")
        while not self._stop_req.isSet():
            self._server.poll()
            if _admin_client != None:
                self._process_commands()
                self._process_queue()

        #shutting down, disconnect the client
        self.disconnect_client()
        self._server.stop()
            
    def join(self, timeout=None):
        """Override join to shut down the server and wait until it exits"""
        self._stop_req.set()
        super(Admin, self).join(timeout)
        
        
