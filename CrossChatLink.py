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

VERSION = "CrossChatLink v0.1.0"
VERSION_NO = "1"
CONFIG_FILE = "config.xml"
LOG_FILE = "ccl.log"

class CrossChatLink(threading.Thread):
    """
    Main thread of the program. Sets up and keeps track of links, parses and processes commands.
    """

    #define the user levels
    USER = 1
    OP = 2
    ADMIN = 4

    #Help database: Dictionary structure is cmd : {permissions: [syntax, help, [valid # of params]], ...}, ...
    helpDB = {"help":{
                ADMIN + OP + USER: ["help [command]", "Prints general help. Specify a command for detailed help", [0, 1]]},
             "about":{
                ADMIN + OP + USER: ["about", "Prints program information", [0]]},
             "update":{
                ADMIN: ["update 'check'|'apply'", "Manages updates. 'check' checks for a new version, apply downloads the update", [1]]},
             "status":{
                ADMIN + OP: ["status [connection]", "Displays the connection status. If no connection is specified, a general overview is displayed", [0, 1]],
                USER: ["status", "Displays a general overview of the connections status", [0]]},
             "exit":{
                ADMIN: ["exit", "Terminates your admin connection", [0]]},
             "shutdown":{
                ADMIN: ["shutdown", "Stops the program", [0]]},
             "connect":{
                ADMIN: ["connect <connection>", "Connects the specified connection", [1]]},
             "disconnect":{
                ADMIN: ["disconnect <connection>", "Disconnects the specified connection", [1]],
                OP: ["disconnect", "Disconnects the connection (careful, theres no getting it back without admin access)", [0]]},
             "reconnect":{
                ADMIN: ["reconnect <connection>", "Reconnects the specified connection", [1]],
                OP: ["reconnect", "Reconnects the connection", [0]]},
             "link":{
                ADMIN: ["link '->'|'<-'|'<->' <connection1> <connection2>", "Links the two connections. The first parameter specifies the direction(s) of the link", [3]],
                OP: ["link <connection>", "Links the current connection to the specified connection", [1]]},
             "unlink":{
                ADMIN: ["unlink '->'|'<-'|'<->' <connection1> <connection2>", "Unlinks the connections. The first parameter specifies the direction(s) to unlink", [3]],
                OP: ["unlink <connection>", "Unlinks the specified connection. This only unlinks the outward link", [1]]},
             "viewusers":{
                ADMIN: ["viewusers <connection>", "Displays a list of configured users and their properties", [1]],
                OP: ["viewusers", "Displays a list of configured users and their properties", [0]]},
             "setuser":{
                ADMIN: ["setuser <connection> <nick> <ignorePM> <ignoreMC> <control>",
                        "Configures a user on a certain connection. The three options must be one of 'y'|'n'|'u' (yes, no, unset).\n"
                        "Note that <ignorePM> and <control> only apply to local users, while <ignoreMC> only applies to external users", [5]],
                OP: ["setuser <nick> <ignorePM> <ignoreMC> <control>",
                     "Configures a user. The three options must be one of 'y'|'n'|'u' (yes, no, unset).\n"
                     "Note that <ignorePM> and <control> only apply to local users, while <ignoreMC> only applies to external users", [4]]},
             "addconnection":{
                ADMIN: ["addconnection <name> <'nmdc'|'adc'|'irc'> <server> <nick> <passwd> <prefix>",
                        "Sets up a new connection. Connection properties can be further refined with 'setconnection'", [6]]},
             "delconnection":{
                ADMIN: ["delconnection <connection>", "Deletes the specified connection", [0]]},
             "setconnection":{
                ADMIN: ["setconnection <connection> [property [value]]", "Sets the <property> of the <connection> to <value>.\n"
                        "If <value> is omitted, it displays the current value. If <property> and <value> are omitted, it displays a list of properties", [1, 2, 3]]}
             }
    
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

    def parseCommand(self, command, source, user, usrLvl):
        """Adds a command to the command queue to be parsed"""
        #sanitize on the way in
        if not usrLvl in [self.USER, self.OP, self.ADMIN]:
            raise ValueError ("Invalid user level passed to command parser")
        
        self._commandQueue.put_nowait((command.lower(), source, user, usrLvl))

    def _doCommand(self, cmd, source, usrLvl):
        """Does actions required by a command and returns the resulting response"""        
        numCmds = len(cmd)

        #Check source connection is still valid
        if (usrLvl != self.ADMIN or source != None) and source not in self.connections:
            return "Error: Source connection is no longer valid"

        #Check command was entered
        if numCmds == 0:
            return "ERROR: No command entered. Try 'help' to show help"

        #check valid command
        if cmd[0] not in self.helpDB:
            return "ERROR: Invalid command entered. Try 'help' to show help"
        
        #check permissions to run command
        temp = [x for x in self.helpDB[cmd[0]] if usrLvl & x != 0]
        if len(temp) == 0:
            return "ERROR: Invalid command entered. Try 'help' to show help"

        #store the permisison level (for accessing the command data)
        cmdLvl = temp[0]
        
        #check correct number of parameters
        if numCmds-1 not in self.helpDB[cmd[0]][cmdLvl][2]:
            return "ERROR: Incorrect number of parameters for '{0}', try 'help {0}' for more info".format(cmd[0])

        #command entered can be executed, start processing it
        if cmd[0] == "help":
            if numCmds == 1:
                rslt = ["Command listing:\n"]
                for helpCmd in sorted(self.helpDB):
                    #only show commands the user has permission to run
                    temp = [x for x in self.helpDB[helpCmd] if usrLvl & x != 0]
                    if len(temp) != 0:
                        rslt.append(self.helpDB[helpCmd][temp[0]][0])
                return "\n".join(rslt)
            else:
                if cmd[1] in self.helpDB:
                    temp = [x for x in self.helpDB[cmd[1]] if usrLvl & x != 0]
                    if len(temp) != 0:
                        return "Syntax: {}\nNotes: {}".format(*self.helpDB[cmd[1]][temp[0]][0:2])
                return "ERROR: Command '{}' doesn't exist".format(cmd[1])

        elif cmd[0] == "about":
            return "{} by pR0Ps\nProject page: https://bitbucket.org/pR0Ps/crosschatlink\nReleased under the GNU GPL 3 licence.".format(VERSION)

        elif cmd[0] == "update":
            if cmd[1] == "check":
                return "TODO: Check for update"
            elif cmd[1] == "apply":
                return "TODO: Apply update (will take into effect next restart)"
            else:
                return "ERROR: 'update' command must specify 'check' or 'apply'"

        elif cmd[0] == "status":
            if numCmds == 1:
                return "TODO: General status"
            else:
                if cmd[1] in self.connections:
                    return "TODO: Detailed status for '{}' connection".format(cmd[1])
                else:
                    return "ERROR: No connection named '{}'".format(cmd[1])

        #exit and shutdown have already been processed
        elif cmd[0] == "connect":
            if cmd[1] in self.connections:
                return "TODO: Connect connection '{}'".format(cmd[1])
            else:
                return "ERROR: No connection named '{}'".format(cmd[1])

        elif cmd[0] == "disconnect":
            if numCmds == 1:
                return "TODO: Disconnect source connection '{}'".format(source)
            else:
                if cmd[1] in self.connections:
                    return "TODO: Disconnect connection '{}'".format(cmd[1])
                else:
                    return "ERROR: No connection named '{}'".format(cmd[1])

        elif cmd[0] == "reconnect":
            if numCmds == 1:
                return "TODO: Reconnect source connection '{}'".format(source)
            else:
                if cmd[1] in self.connections:
                    return "TODO: Reconnect connection '{}'".format(cmd[1])
                else:
                    return "ERROR: No connection named '{}'".format(cmd[1])

        elif cmd[0] == "link":
            if numCmds == 2:
                if source == cmd[1]:
                    return "ERROR: No local links"
                if cmd[1] in self.connections:
                    return "TODO: Link source connection ('{}') ---> {}".format(source, cmd[1])
                else:
                    return "ERROR: No connection named '{}'".format(cmd[1])
            else:
                #check connections are valid
                if cmd[2] == cmd[3]:
                    return "ERROR: No local links"
                for x in range(2, 4):
                    if cmd[x] not in self.connections:
                        return "ERROR: No connection named '{}'".format(cmd[x])
                if cmd[1] == "->":
                    return "TODO: Link '{}' ---> '{}'".format(*cmd[2:])
                elif cmd[1] == "<-":
                    return "TODO: Link '{}' <--- '{}'".format(*cmd[2:])
                elif cmd[1] == "<->":
                    return "TODO: Link '{}' <---> '{}'".format(*cmd[2:])
                else:
                    return "ERROR: Link direction must be '<-', '->', or '<->'"

        elif cmd[0] == "unlink":
            if numCmds == 2:
                if cmd[1] in self.connections:
                    return "TODO: Unlink source connection ('{}') ---> {}".format(source, cmd[1])
                else:
                    return "ERROR: No connection named '{}'".format(cmd[1])
            else:
                for x in range(2, 4):
                    if cmd[x] not in self.connections:
                        return "ERROR: No connection named '{}'".format(cmd[x])
                if cmd[1] == "->":
                    return "TODO: Unlink '{}' ---> '{}'".format(*cmd[2:])
                elif cmd[1] == "<-":
                    return "TODO: Un;ink '{}' <--- '{}'".format(*cmd[2:])
                elif cmd[1] == "<->":
                    return "TODO: Unlink '{}' <---> '{}'".format(*cmd[2:])
                else:
                    return "ERROR: Unlink direction must be '<-', '->', or '<->'"

        elif cmd[0] == "viewusers":
            if numCmds == 1:
                return "TODO: List all users of source connection ('{}')".format(source)
            else:
                if cmd[1] in self.connections:
                    return "TODO: List all users of connection '{}'".format(cmd[1])
                else:
                    return "ERROR: No connection named '{}'".format(cmd[1])

        elif cmd[0] == "setuser":
            for x in range (numCmds - 3, numCmds):
                if cmd[x] != "y" and cmd[x] != "n" and cmd[x] != "u":
                    return "ERROR: Invalid setting specified, must be 'y', 'n', or 'u' (yes/no/unset)"
            if numCmds == 5:
                return "TODO: add user '{}' to settings as {}/{}/{}".format(*cmd[1:])
            else:
                if cmd[1] in self.connections:
                    return "TODO: add user '{}' to settings as {}/{}/{}".format(*cmd[2:])
                else:
                    return "ERROR: No connection named '{}'".format(cmd[1])

        elif cmd[0] == "addconnection":
            if cmd[1] in self.connections:
                return "ERROR: Connection '{}' already exists, delete it first with 'delconnection'".format(cmd[1])
            if cmd[2] == "nmdc":
                return "TODO: Add an NMDC hub (server: {}, nick: {}, passwd: {}, prefix: {})".format(*cmd[3:])
            elif cmd[2] == "adc":
                return "TODO: Add an ADC hub (server: {}, nick: {}, passwd: {}, prefix: {})".format(*cmd[3:])
            elif cmd[2] == "irc":
                return "TODO: Add an IRC server (server: {}, nick: {}, passwd: {}, prefix: {})".format(*cmd[3:])
            else:
                return "ERROR: '{}' is not a valid connection type".format(cmd[2])
            
        elif cmd[0] == "delconnection":
            if cmd[1] in self.connections:
                return "TODO: Detele connection '{}'".format(cmd[1])
            else:
                return "ERROR: No connection named '{}'".format(cmd[1])
            
        elif cmd[0] == "setconnection":
            #setconnection <connection> [property [value]]
            if cmd[1] not in self.connections:
                return "ERROR: No connection named '{}'".format(cmd[1])

            #set availible attributes
            attrs = ["server", "nick", "passwd", "autoConnect", "autoReconnect", "mcRate", "pmRate", "opControl"]
            temp = type(self.connections[cmd[1]])
            if temp == links.ADC or temp == links.NMDC:
                attrs.extend(["share", "slots", "client"])
            else:
                attrs.extend(["identText", "channels", "connectCmds"])
                
            if numCmds == 2:
                #return a list of attributes
                return "Attributes of '{}':\n".format(cmd[1]) + "\n".join(attrs)
            elif numCmds == 3:
                #display current setting
                if cmd[2] in attrs:
                    return "'{}' attribute of '{}' is: {}".format(cmd[2], cmd[1], getattr(self.connections[cmd[1]], cmd[2]))
                else:
                    return "ERROR: No attribute '{}' for connection '{}'".format(cmd[2], cmd[1])
            else:
                #set attribute
                if cmd[2] in attrs:
                    return "TODO: Set '{}' attribute of connection '{}' to: {}".format(cmd[2], cmd[1], cmd[3])
                else:
                    return "ERROR: No attribute '{}' for connection '{}'".format(cmd[2], cmd[1])
                                                                
        

        logging.critical("helpDB incorrectly configured, let {} through, but it didn't match any if statements".format(cmd[0]))
        
    def _processQueue(self):
        """Takes the next item from the queue and processes it"""
        try:
            #blocks until something is in the queue
            temp = self._commandQueue.get(True, 5)
        except queue.Empty as e:
            return False
        #unpack the tuple
        command, source, user, usrLvl = temp

        #post-response flags (processed *after* sending data to client)
        shutdown, disconnect = False, False

        #split the command up into tokens
        try:
            params = shlex.split(command)
        except ValueError:
            return True
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
            response = self._doCommand(params, source, usrLvl)

        #send the response
        if source == None: #admin interface
            self.adminInterface.msgQueue.put_nowait(response)
            if disconnect:
                self.adminInterface.disconnectClient()
        elif source in self.connections:
            self.connections[source].sendPM(response, user)
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

    
