
import threading
import logging
import queue

import miniboa

#Client connected via telnet
_adminClient = None

#connect and disconnect handlers
def onConnect(client):
    global _adminClient
    logging.info("Client connected from {}".format(client.addrport()))
    _adminClient = client
    _adminClient.send("Welcome to the CrossChatLink admin interface!"
                         "\n\nType 'help' or '?' for a list of commands\n\n")
def onDisconnect(client):
    global _adminClient
    logging.info ("Client disconnected")
    _adminClient = None

class Admin (threading.Thread):
    """
    Provides an admin interface via a telnet server
    """

    def __init__(self, program):
        super(Admin, self).__init__()
        self._program = program
        self._telnetServer = miniboa.TelnetServer(23, "127.0.0.1", onConnect,
                                                 onDisconnect, 1, 0.3)
        self._stopReq = threading.Event()
        self.msgQueue = queue.Queue()
        
    def _processCommands(self):
        """Recieves a line from the client and proccesses it (assumes valid client)"""
        if _adminClient.active and _adminClient.cmd_ready:
            msg = _adminClient.get_command()
            #add command to the queue (None for link/user = admin interface)
            self._program.parseCommand(msg, None, None, self._program.ADMIN)

    def disconnectClient(self):
        """Sends all messages and disconnects the client"""
        logging.debug("Disconnecting client")
        if _adminClient != None:
            while self._processQueue():
                pass

            #update the client so they get the messages
            self._telnetServer.poll()
            _adminClient.deactivate()
            #update so the client is disconnected
            self._telnetServer.poll()
        
    def _processQueue(self):
        """Sends messages in the queue to the client (assumes valid client)"""
        if self.msgQueue.qsize() == 0:
            return False
        try:
            _adminClient.send(self.msgQueue.get_nowait() + "\n")
            return True
        except queue.Empty as e:
            pass
        return False

    def run(self):
        """Starts the telnet server"""
        logging.info ("Starting telnet server")
        while not self._stopReq.isSet():
            self._telnetServer.poll()
            if _adminClient != None:
                self._processCommands()
                self._processQueue()

        #shutting down, disconnect the client
        self.disconnectClient()
        self._telnetServer.stop()
            
    def join(self, timeout=None):
        """Override join to shut down the server and wait until it exits"""
        self._stopReq.set()
        super(Admin, self).join(timeout)
        
        
