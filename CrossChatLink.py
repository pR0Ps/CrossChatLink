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
        self._stop_req = threading.Event()
        
        logging.info ("Starting " + VERSION)

        #stores commands to process
        self._command_queue = queue.Queue()

        #create the telnet thread
        self.admin_interface = interface.Admin(self)
        self.admin_interface.start()

        #create the initial connection dict
        self.connections = dict()

    def load_config(self):
        """Loads the configuration file and sets up the links"""
        logging.debug("Loading configuration data")
        #TODO: load XML file with settings in it
        #TODO: create/configure the link threads
        logging.debug("Setting up links")

        #testing
        self.connections["nmdc"] = links.NMDC(self, "127.0.0.1:443", "Nick", "aPass", "[NMDC]")
        self.connections["adc"] = links.ADC(self, "127.0.0.1:443", "Nick", "aPass", "[ADC]")
        self.connections["irc"] = links.IRC(self, "127.0.0.1:6667", "Nick", "aPass", "[IRC]")
        self.connections["nmdc"].add_links("nmdc", ["adc", "irc"])
        self.connections["adc"].add_links("adc", ["irc"])
        self.connections["irc"].add_links("irc", ["nmdc"])

    def save_config(self):
        """Saves the current configuration to a file"""
        #TODO: get data from all links
        #TODO: save XML file
        pass

    def auto_connect(self):
        """Starts the links that are set to autoconnect"""
        logging.debug ("Autoconnecting links...")
        for link in self.connections.values():
            if link.auto_connect:
                link.start()

    def link_structure(self, connection, split_both):
        """
        Returns a dict of [in, out] describing how the connection is linked.
        If splitBoth is true, 'both' will be added to keys and 2 way links
        will be stored in it instead
        """
        
        #get connections that link to the specified one
        links_in = [x for x in self.connections if connection in self.connections[x].links]

        temp_in = []
        temp_out = []
        if split_both:
            temp_both = []

        #add incoming links
        temp_in = [x for x in links_in if x not in self.connections[connection].links]
            
        #add links just out and links both ways
        for out in self.connections[connection].links:
            if out in links_in:
                if split_both:
                    temp_both.append(out)
                else:
                    temp_in.append(out)
                    temp_out.append(out)
            else:
                temp_out.append(out)
        if split_both:
            return {"in": sorted(temp_in), "out": sorted(temp_out), "both" : sorted(temp_both)}
        else:
            return {"in": sorted(temp_in), "out": sorted(temp_out)}

    def parse_command(self, command, source, user, usr_lvl):
        """Adds a command to the command queue to be parsed"""
        #sanitize on the way in
        if not usr_lvl in [self.USER, self.OP, self.ADMIN]:
            raise ValueError ("Invalid user level passed to command parser")
        
        self._command_queue.put_nowait((command, source, user, usr_lvl))

    def _do_command(self, cmd, source, usr_lvl):
        """Does actions required by a command and returns the resulting response"""        
        num_cmds = len(cmd)

        #Check source connection is still valid
        if (usr_lvl != self.ADMIN or source != None) and source not in self.connections:
            return "Error: Source connection is no longer valid"

        #Check command was entered
        if num_cmds == 0:
            return "ERROR: No command entered. Try 'help' to show help"

        #check valid command
        if cmd[0] not in self.helpDB:
            return "ERROR: Invalid command entered. Try 'help' to show help"
        
        #check permissions to run command
        temp = [x for x in self.helpDB[cmd[0]] if usr_lvl & x != 0]
        if len(temp) == 0:
            return "ERROR: Invalid command entered. Try 'help' to show help"

        #store the permisison level (for accessing the command data)
        cmd_lvl = temp[0]
        
        #check correct number of parameters
        if num_cmds-1 not in self.helpDB[cmd[0]][cmd_lvl][2]:
            return "ERROR: Incorrect number of parameters for '{0}', try 'help {0}' for more info".format(cmd[0])

        #case-insensitive commands
        cmd[0] = cmd[0].lower()

        #command entered can be executed, start processing it
        if cmd[0] == "help":
            if num_cmds == 1:
                rslt = ["Command listing:\n"]
                for help_cmd in sorted(self.helpDB):
                    #only show commands the user has permission to run
                    temp = [x for x in self.helpDB[help_cmd] if usr_lvl & x != 0]
                    if len(temp) != 0:
                        rslt.append(self.helpDB[help_cmd][temp[0]][0])
                return "\n".join(rslt)
            else:
                cmd[1] = cmd[1].lower()
                if cmd[1] in self.helpDB:
                    temp = [x for x in self.helpDB[cmd[1]] if usr_lvl & x != 0]
                    if len(temp) != 0:
                        return "Syntax: {}\nNotes: {}".format(*self.helpDB[cmd[1]][temp[0]][0:2])
                return "ERROR: Command '{}' doesn't exist".format(cmd[1])

        elif cmd[0] == "about":
            return "{} by pR0Ps\nProject page: https://bitbucket.org/pR0Ps/crosschatlink\nReleased under the GNU GPL 3 licence.".format(VERSION)

        elif cmd[0] == "update":
            cmd[1] = cmd[1].lower()
            if cmd[1] == "check":
                return "TODO: Check for update"
            elif cmd[1] == "apply":
                return "TODO: Apply update (will take into effect next restart)"
            else:
                return "ERROR: 'update' command must specify 'check' or 'apply'"

        elif cmd[0] == "status":
            if num_cmds == 1:
                #line sperator
                sep = "+{0:-<9}+{0:-<5}+{0:-<28}+{0:-<6}+{0:-<9}+{0:-<9}+".format("")
                #header
                temp_ret = ["General status:\n\n{0}\n|{1:9}|{2:5}|{3:28}|{4:6}|{5:9}|{6:9}|\n{0}".format(sep, "Name", "Type", "Server", "State", "Links out", "Links in")]
                for con_name in sorted(self.connections):
                    #add connection data
                    con_obj = self.connections[con_name]
                    link_struct = self.link_structure(con_name, False)
                    num_links = max(len(link_struct["in"]), len(link_struct["out"]))
                    
                    for i in range (0, num_links):
                        link_out = link_struct["out"][i] if i < len(link_struct["out"]) else ""
                        link_in = link_struct["in"][i] if i < len(link_struct["in"]) else ""
                        if i == 0:
                            #first line
                            con_type = "IRC" if type(con_obj) == links.IRC else ("NMDC" if type(con_obj) == links.NMDC else "ADC")
                            temp_ret.append("|{:9}|{:5}|{:28}|{:6}|{:9}|{:9}|".format(con_name, con_type, con_obj.server, con_obj.connection_state, link_out, link_in))
                        else:
                            #secondary lines
                            temp_ret.append("|{0:9}|{0:5}|{0:28}|{0:6}|{1:9}|{2:9}|".format("", link_out, link_in))
                    #seperator
                    temp_ret.append(sep)
                return "\n".join(temp_ret)
            else:
                cmd[1] = cmd[1].lower()
                if cmd[1] in self.connections:
                    con_obj = self.connections[cmd[1]]
                    con_type = "IRC" if type(con_obj) == links.IRC else ("NMDC" if type(con_obj) == links.NMDC else "ADC")
                    return "Status for {} connection '{}':\n\n".format(con_type, cmd[1]) + \
                        "Server: {}\nNick: {}\nPassword: {}\nPrefix: {}\n".format(con_obj.server, con_obj.nick, con_obj.passwd, con_obj.prefix) + \
                        "Connect on startup: {}\nAuto reconnect: {}\nPost rate (main): {}\nPost rate (private): {}\n".format(con_obj.auto_connect, con_obj.auto_reconnect, con_obj.mc_rate, con_obj.pm_rate) + \
                        ("Channels to join: {}\nIdent text: {}\nConnect command(s):\n{}".format(con_obj.channels, con_obj.ident_text, con_obj.connect_cmds) if con_type == "IRC" \
                        else "Reported share: {}\nReported slots: {}\nReported client: {}".format(con_obj.share, con_obj.slots, con_obj.client))
                else:
                    return "ERROR: No connection named '{}'".format(cmd[1])

        #exit and shutdown have already been processed
        elif cmd[0] == "connect":
            cmd[1] = cmd[1].lower()
            if cmd[1] in self.connections:
                return "TODO: Connect connection '{}'".format(cmd[1])
            else:
                return "ERROR: No connection named '{}'".format(cmd[1])

        elif cmd[0] == "disconnect":
            if num_cmds == 1:
                return "TODO: Disconnect source connection '{}'".format(source)
            else:
                cmd[1] = cmd[1].lower()
                if cmd[1] in self.connections:
                    return "TODO: Disconnect connection '{}'".format(cmd[1])
                else:
                    return "ERROR: No connection named '{}'".format(cmd[1])

        elif cmd[0] == "reconnect":
            if num_cmds == 1:
                return "TODO: Reconnect source connection '{}'".format(source)
            else:
                cmd[1] = cmd[1].lower()
                if cmd[1] in self.connections:
                    return "TODO: Reconnect connection '{}'".format(cmd[1])
                else:
                    return "ERROR: No connection named '{}'".format(cmd[1])

        elif cmd[0] == "link":
            if num_cmds == 2:
                cmd[1] = cmd[1].lower()
                if source == cmd[1]:
                    return "ERROR: No local links"
                if cmd[1] in self.connections:
                    return "TODO: Link source connection ('{}') ---> {}".format(source, cmd[1])
                else:
                    return "ERROR: No connection named '{}'".format(cmd[1])
            else:
                #check connections are valid
                cmd[2] = cmd[2].lower()
                cmd[3] = cmd[3].lower()
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
            if num_cmds == 2:
                cmd[1] = cmd[1].lower()
                if cmd[1] in self.connections:
                    return "TODO: Unlink source connection ('{}') ---> {}".format(source, cmd[1])
                else:
                    return "ERROR: No connection named '{}'".format(cmd[1])
            else:
                for x in range(2, 4):
                    cmd[x] = cmd[x].lower()
                    if cmd[x] not in self.connections:
                        return "ERROR: No connection named '{}'".format(cmd[x])
                if cmd[1] == "->":
                    return "TODO: Unlink '{}' ---> '{}'".format(*cmd[2:])
                elif cmd[1] == "<-":
                    return "TODO: Unlink '{}' <--- '{}'".format(*cmd[2:])
                elif cmd[1] == "<->":
                    return "TODO: Unlink '{}' <---> '{}'".format(*cmd[2:])
                else:
                    return "ERROR: Unlink direction must be '<-', '->', or '<->'"

        elif cmd[0] == "viewusers":
            if num_cmds == 1:
                return "TODO: List all users of source connection ('{}')".format(source)
            else:
                cmd[1] = cmd[1].lower()
                if cmd[1] in self.connections:
                    return "TODO: List all users of connection '{}'".format(cmd[1])
                else:
                    return "ERROR: No connection named '{}'".format(cmd[1])

        elif cmd[0] == "setuser":
            for x in range (num_cmds - 3, num_cmds):
                cmd[x] = cmd[x].lower()
                if cmd[x] != "y" and cmd[x] != "n" and cmd[x] != "u":
                    return "ERROR: Invalid setting specified, must be 'y', 'n', or 'u' (yes/no/unset)"
            if num_cmds == 5:
                return "TODO: add user '{}' to settings as {}/{}/{}".format(*cmd[1:])
            else:
                cmd[1] = cmd[1].lower()
                if cmd[1] in self.connections:
                    return "TODO: add user '{}' to settings as {}/{}/{}".format(*cmd[2:])
                else:
                    return "ERROR: No connection named '{}'".format(cmd[1])

        elif cmd[0] == "addconnection":
            cmd[1] = cmd[1].lower()
            cmd[2] = cmd[2].lower()
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
            cmd[1] = cmd[1].lower()
            if cmd[1] in self.connections:
                return "TODO: Detele connection '{}'".format(cmd[1])
            else:
                return "ERROR: No connection named '{}'".format(cmd[1])
            
        elif cmd[0] == "setconnection":
            #setconnection <connection> [property [value]]
            cmd[1] = cmd[1].lower()
            if cmd[1] not in self.connections:
                return "ERROR: No connection named '{}'".format(cmd[1])

            #set availible attributes
            attrs = ["server", "nick", "passwd", "auto_connect", "auto_reconnect", "mc_rate", "pm_rate", "op_control"]
            temp = type(self.connections[cmd[1]])
            if temp == links.ADC or temp == links.NMDC:
                attrs.extend(["share", "slots", "client"])
            else:
                attrs.extend(["ident_text", "channels", "connect_cmds"])
                
            if num_cmds == 2:
                #return a list of attributes
                return "Attributes of '{}':\n".format(cmd[1]) + "\n".join(attrs)
            elif num_cmds == 3:
                cmd[2] = cmd[2].lower()
                #display current setting
                if cmd[2] in attrs:
                    return "'{}' attribute of '{}' is: {}".format(cmd[2], cmd[1], getattr(self.connections[cmd[1]], cmd[2]))
                else:
                    return "ERROR: No attribute '{}' for connection '{}'".format(cmd[2], cmd[1])
            else:
                cmd[2] = cmd[2].lower()
                #set attribute
                if cmd[2] in attrs:
                    return "TODO: Set '{}' attribute of connection '{}' to: {}".format(cmd[2], cmd[1], cmd[3])
                else:
                    return "ERROR: No attribute '{}' for connection '{}'".format(cmd[2], cmd[1])
                                                                
        

        logging.critical("helpDB incorrectly configured, let {} through, but it didn't match any if statements".format(cmd[0]))
        
    def _process_queue(self):
        """Takes the next item from the queue and processes it"""
        try:
            #blocks until something is in the queue
            temp = self._command_queue.get(True, 5)
        except queue.Empty as e:
            return False
        #unpack the tuple
        command, source, user, usr_lvl = temp

        #post-response flags (processed *after* sending data to client)
        shutdown, disconnect = False, False

        #split the command up into tokens
        try:
            params = shlex.split(command)
        except ValueError:
            return True
        logging.debug("Command recieved: " + str(params))

        #Check for post-response actions
        if len(params) == 1 and params[0] == "shutdown" and usr_lvl == self.ADMIN:
            shutdown = True
            response = "Shutting down the server..."
        elif len(params) == 1 and params[0] == "exit" and usr_lvl == self.ADMIN:
            disconnect = True
            response = "You are being disconnected (server is still running)"
        else:
            #general command processing
            response = self._do_command(params, source, usr_lvl)

        #send the response
        if source == None: #admin interface
            self.admin_interface.msg_queue.put_nowait(response)
            if disconnect:
                self.admin_interface.disconnect_client()
        elif source in self.connections:
            self.connections[source].send_PM(response, user)
        else:
            logging.warning("Attempted to send command response to invalid link")

        #shutdown
        if shutdown:
            self.stop()

        return True

    def shutdown(self):
        """Shut. Down. Everything."""
        logging.info("Shutting down admin interface")
        self.admin_interface.join()
        logging.info("Shutting down links")
        for link in self.connections.values():
            link.join()
        logging.info("All threads terminated, exiting")

    def stop(self):
        """Tells the program it's time to exit"""
        logging.debug ("Telling the program to exit")
        self._stop_req.set()

    def run(self):
        """Proccesses the actions sent to it"""
        while not self._stop_req.isSet():
            self._process_queue()

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
    instance.load_config()
    instance.auto_connect()
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

    
