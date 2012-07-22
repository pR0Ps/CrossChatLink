#!/usr/bin/python

# CrossChatLink
# A cross platform chat linker for DC hubs and IRC channels

import interface
import links
import logging
import threading
import queue
import shlex
import time

VERSION = "CrossChatLink Alpha"
CONFIG_FILE = "config.xml"
LOG_FILE = "ccl.log"

class CrossChatLink(threading.Thread):
    """
    Main thread of the program. Sets up and keeps track of links, parses and processes commands.
    """

    #define the user levels
    USER = 0
    OP = 1
    ADMIN = 2
    
    def __init__(self):
        super(CrossChatLink, self).__init__()
        self._stopReq = threading.Event()
        
        logging.info ("Starting " + VERSION)

        #stores commands to process
        self._commandQueue = queue.Queue()

        #create the telnet thread
        self.adminInterface = interface.Admin(self)
        self.adminInterface.start()

        #create the initial connection dict
        self.connections = dict()

    def loadConfig(self):
        """Loads the configuration file and sets up the links"""
        logging.debug("Loading configuration data")
        #TODO: load XML file with settings in it
        #TODO: create/configure the link threads
        logging.debug("Setting up links")
        self.connections["nmdctest"] = links.NMDC(self, "127.0.0.1:443", "Nick", "aPass", "[NMDC]")
        self.connections["adctest"] = links.ADC(self, "127.0.0.1:443", "Nick", "aPass", "[ADC]")
        self.connections["irctest"] = links.IRC(self, "irc.esper.net:6667", "Nick", "aPass", "[IRC]")

    def saveConfig(self):
        """Saves the current configuration to a file"""
        #TODO: get data from all links
        #TODO: save XML file
        pass

    def autoConnect(self):
        """Starts the links that are set to autoconnect"""
        logging.debug ("Autoconnecting links...")
        for link in self.connections.values():
            if link.autoConnect:
                link.start()

    def parseCommand(self, command, link, user, usrLvl):
        """Adds a command to the command queue to be parsed"""
        #sanitize on the way in
        if not usrLvl in [self.USER, self.OP, self.ADMIN]:
            raise ValueError ("Invalid user level passed to command parser")
        
        self._commandQueue.put_nowait((command.lower(), link, user, usrLvl))

    def _doCommand(self, cmd, usrLvl):
        """Does actions required by a command and returns the resulting response"""
        #TODO: Flesh this out
        if usrLvl == self.ADMIN:
            #administrator
            pass
        if usrLvl == self.ADMIN or usrLvl == self.OP:
            #OP user
            pass
        if usrLvl == self.ADMIN or usrLvl == self.OP or usrLvl == self.USER:
            #normal user
            if len(cmd) == 1:
                if cmd[0] == "?" or cmd[0] == "help":
                    return "TODO: HELP TEXT"

        #default catch-all
        return "Invalid command entered. Try '?' or 'help' to show help"

    def _processQueue(self):
        """Takes the next item from the queue and processes it"""
        try:
            #blocks until something is in the queue
            temp = self._commandQueue.get(True, 5)
        except queue.Empty as e:
            return False
        #unpack the tuple
        command, link, user, usrLvl = temp

        #post-response flags (processed *after* sending data to client)
        shutdown, disconnect = False, False

        #split the command up into tokens
        params = shlex.split(command)
        logging.debug("Command recieved: " + str(params))

        #Check for post-response actions
        if len(params) == 1 and params[0] == "shutdown" and usrLvl == self.ADMIN:
            shutdown = True
            response = "Shutting down the server..."
        elif len(params) == 1 and params[0] == "exit" and usrLvl == self.ADMIN:
            disconnect = True
            response = "You are being disconnected (server is still running)"
        else:
            #general command processing
            response = self._doCommand(params, usrLvl)

        #send the response
        if link == None: #admin interface
            self.adminInterface.msgQueue.put_nowait(response)
            if disconnect:
                self.adminInterface.disconnectClient()
        elif link in self.connections:
            self.connections[link].sendPM(response, user)
        else:
            logging.warning("Attempted to send command response to invalid link")

        #shutdown
        if shutdown:
            self.stop()

        return True

    def shutdown(self):
        """Shut. Down. Everything."""
        logging.info("Shutting down admin interface")
        self.adminInterface.join()
        logging.info("Shutting down links")
        for link in self.connections.values():
            link.join()
        logging.info("All threads terminated, exiting")

    def stop(self):
        """Tells the program it's time to exit"""
        logging.debug ("Telling the program to exit")
        self._stopReq.set()

    def run(self):
        """Proccesses the actions sent to it"""
        while not self._stopReq.isSet():
            self._processQueue()

        logging.info("Shutting down...")
        self.shutdown()
        

if __name__ == "__main__":
    # specify --log=DEBUG/INFO/WARN/ERROR/CRITICAL as a param (defaults to WARN)
    try:
        temp = int(getattr(logging, loglevel.upper(), None))
    except Exception as e:
        temp = logging.DEBUG
        
    logging.basicConfig(filename=LOG_FILE, level=temp, format="%(asctime)s-%(levelname)s: %(message)s (%(filename)s)")
    logging.critical("Program started")
    print("Program started, press CTRL-C to exit")

    instance = CrossChatLink()
    instance.loadConfig()
    instance.autoConnect()
    instance.start()

    #Wait until the main thread exits (or throws an exception)
    try:
        while instance.isAlive():
            instance.join(2)
    except:
        print("Exiting...")
        instance.stop()
        instance.join()

    logging.critical("Program exited succesfully")
    print("Program exited succesfully")

    
